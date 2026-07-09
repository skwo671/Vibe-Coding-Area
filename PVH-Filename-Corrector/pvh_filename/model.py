from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
from transformers import CLIPModel, CLIPProcessor

from pvh_filename.dataset import build_records
from pvh_filename.filenames import parse_suffix_components, suffix_kind


class ImagePathDataset(Dataset):
    def __init__(self, paths: list[str], labels: list[int] | None = None):
        self.paths = paths
        self.labels = labels

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, idx: int):
        if self.labels is None:
            return self.paths[idx]
        return self.paths[idx], self.labels[idx]


class ClipEmbedder:
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32", batch_size: int = 16):
        self.device = "mps" if torch.backends.mps.is_available() else (
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        self.batch_size = batch_size
        self.processor = CLIPProcessor.from_pretrained(model_name)
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        self.model.eval()

    @torch.inference_mode()
    def encode_paths(self, paths: list[str]) -> tuple[np.ndarray, list[str]]:
        embeddings: list[np.ndarray] = []
        valid_paths: list[str] = []
        dataset = ImagePathDataset(paths)
        loader = DataLoader(dataset, batch_size=self.batch_size, shuffle=False)

        for batch_paths in tqdm(loader, desc="Embedding images", unit="batch"):
            images = []
            batch_valid: list[str] = []
            for path in batch_paths:
                try:
                    with Image.open(path) as img:
                        images.append(img.convert("RGB"))
                    batch_valid.append(path)
                except OSError as exc:
                    tqdm.write(f"Skip unreadable image ({exc}): {path}")

            if not images:
                continue

            inputs = self.processor(images=images, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            features = self.model.get_image_features(**inputs)
            if not isinstance(features, torch.Tensor):
                features = features.pooler_output
            features = features / features.norm(dim=-1, keepdim=True)
            embeddings.append(features.cpu().numpy())
            valid_paths.extend(batch_valid)

        if not embeddings:
            raise ValueError("No readable images found for embedding.")
        return np.vstack(embeddings), valid_paths


def _make_classifier() -> LogisticRegression:
    return LogisticRegression(max_iter=3000, class_weight="balanced", n_jobs=-1)


def _fit_encoder_model(
    embeddings: np.ndarray,
    labels: list[str],
    min_samples: int = 2,
) -> tuple[LabelEncoder, LogisticRegression, dict]:
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    keep = {label for label, count in counts.items() if count >= min_samples}
    idx = [i for i, label in enumerate(labels) if label in keep]
    if len(idx) < 10 or len(keep) < 2:
        encoder = LabelEncoder()
        encoder.fit(["__none__"])
        model = _make_classifier()
        model.fit(np.zeros((1, embeddings.shape[1])), [0])
        return encoder, model, {"train_accuracy": 0.0, "val_accuracy": 0.0, "num_classes": 0}

    sub_emb = embeddings[idx]
    sub_labels = [labels[i] for i in idx]
    encoder = LabelEncoder()
    encoded = encoder.fit_transform(sub_labels)
    x_train, x_val, y_train, y_val = train_test_split(
        sub_emb, encoded, test_size=0.15, random_state=42, stratify=encoded
    )
    model = _make_classifier()
    model.fit(x_train, y_train)
    return encoder, model, {
        "train_accuracy": model.score(x_train, y_train),
        "val_accuracy": model.score(x_val, y_val),
        "num_classes": len(encoder.classes_),
    }


class HierarchicalClassifier:
    """Three-stage: color vs angle, then specialized suffix prediction."""

    def __init__(self):
        self.kind_encoder = LabelEncoder()
        self.angle_encoder = LabelEncoder()
        self.color_encoder = LabelEncoder()
        self.kind_model = _make_classifier()
        self.angle_model = _make_classifier()
        self.color_model = _make_classifier()

    def fit(self, embeddings: np.ndarray, suffixes: list[str]) -> dict:
        kinds = [suffix_kind(s) for s in suffixes]
        kind_encoded = self.kind_encoder.fit_transform(kinds)
        x_train, x_val, y_train, y_val = train_test_split(
            embeddings, kind_encoded, test_size=0.15, random_state=42, stratify=kind_encoded
        )
        self.kind_model.fit(x_train, y_train)

        angle_idx = [i for i, k in enumerate(kinds) if k == "angle"]
        color_idx = [i for i, k in enumerate(kinds) if k == "color"]

        angle_labels = [suffixes[i] for i in angle_idx]
        color_labels = [suffixes[i] for i in color_idx]

        self.angle_encoder, self.angle_model, angle_metrics = _fit_encoder_model(
            embeddings[angle_idx], angle_labels
        )
        self.color_encoder, self.color_model, color_metrics = _fit_encoder_model(
            embeddings[color_idx], color_labels
        )

        return {
            "kind_train_accuracy": self.kind_model.score(x_train, y_train),
            "kind_val_accuracy": self.kind_model.score(x_val, y_val),
            "num_kind_classes": len(self.kind_encoder.classes_),
            "angle_train_accuracy": angle_metrics["train_accuracy"],
            "angle_val_accuracy": angle_metrics["val_accuracy"],
            "num_angle_classes": angle_metrics["num_classes"],
            "color_train_accuracy": color_metrics["train_accuracy"],
            "color_val_accuracy": color_metrics["val_accuracy"],
            "num_color_classes": color_metrics["num_classes"],
        }

    def predict(self, embeddings: np.ndarray) -> tuple[list[str], list[str], list[float]]:
        kind_probs = self.kind_model.predict_proba(embeddings)
        kind_idx = kind_probs.argmax(axis=1)
        kinds = [self.kind_encoder.classes_[i] for i in kind_idx]
        kind_conf = [float(kind_probs[i, kind_idx[i]]) for i in range(len(kind_idx))]

        suffixes: list[str] = []
        predicted_kinds: list[str] = []
        confidences: list[float] = []

        angle_classes = list(getattr(self.angle_encoder, "classes_", []))
        color_classes = list(getattr(self.color_encoder, "classes_", []))

        for i, kind in enumerate(kinds):
            emb = embeddings[i : i + 1]
            if kind == "color":
                if color_classes and "__none__" not in color_classes:
                    probs = self.color_model.predict_proba(emb)[0]
                    idx = int(probs.argmax())
                    learned_suffix = color_classes[idx]
                    light_source, _ = parse_suffix_components(learned_suffix)
                    suffix = f"{light_source}_COLOR_CODE"
                    conf = kind_conf[i] * float(probs[idx])
                else:
                    suffix = "COLOR_CODE"
                    conf = kind_conf[i] * 0.1
            elif angle_classes and "__none__" not in angle_classes:
                probs = self.angle_model.predict_proba(emb)[0]
                idx = int(probs.argmax())
                suffix = angle_classes[idx]
                conf = kind_conf[i] * float(probs[idx])
            else:
                suffix = "CORNER"
                conf = kind_conf[i] * 0.1

            suffixes.append(suffix)
            predicted_kinds.append(kind)
            confidences.append(conf)

        return suffixes, predicted_kinds, confidences

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "kind_encoder": self.kind_encoder,
                "angle_encoder": self.angle_encoder,
                "color_encoder": self.color_encoder,
                "kind_model": self.kind_model,
                "angle_model": self.angle_model,
                "color_model": self.color_model,
            },
            path,
        )

    @classmethod
    def load(cls, path: Path) -> "HierarchicalClassifier":
        payload = joblib.load(path)
        obj = cls()
        obj.kind_encoder = payload["kind_encoder"]
        obj.angle_encoder = payload["angle_encoder"]
        obj.color_encoder = payload["color_encoder"]
        obj.kind_model = payload["kind_model"]
        obj.angle_model = payload["angle_model"]
        obj.color_model = payload["color_model"]
        return obj


SuffixClassifier = HierarchicalClassifier


def default_model_path(output_dir: Path) -> Path:
    hierarchical = output_dir / "hierarchical_classifier.joblib"
    if hierarchical.exists():
        return hierarchical
    legacy = output_dir / "suffix_classifier.joblib"
    if legacy.exists():
        return legacy
    return hierarchical


def train_suffix_model(data_root: Path, output_dir: Path, min_samples_per_class: int = 2) -> dict:
    records = build_records(data_root)
    train_rows = [r for r in records if r.suffix and r.suffix_kind in {"color", "angle"}]
    suffix_counts: dict[str, int] = {}
    for row in train_rows:
        suffix_counts[row.suffix] = suffix_counts.get(row.suffix, 0) + 1

    filtered = [r for r in train_rows if suffix_counts[r.suffix] >= min_samples_per_class]
    if not filtered:
        raise ValueError("No training samples left after filtering by min_samples_per_class.")

    paths = [str(r.path) for r in filtered]
    labels = [r.suffix for r in filtered]

    embedder = ClipEmbedder()
    embeddings, valid_paths = embedder.encode_paths(paths)
    path_to_label = dict(zip(paths, labels, strict=False))
    labels = [path_to_label[p] for p in valid_paths]

    classifier = HierarchicalClassifier()
    metrics = classifier.fit(embeddings, labels)

    output_dir.mkdir(parents=True, exist_ok=True)
    classifier.save(output_dir / "hierarchical_classifier.joblib")
    np.save(output_dir / "train_paths.npy", np.array(valid_paths))
    np.save(output_dir / "train_labels.npy", np.array(labels))

    metrics.update(
        {
            "num_images": len(valid_paths),
            "filtered_out_classes": sum(1 for c, n in suffix_counts.items() if n < min_samples_per_class),
            "output_dir": str(output_dir),
            "model_file": str(output_dir / "hierarchical_classifier.joblib"),
        }
    )
    return metrics
