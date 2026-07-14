from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from pvh_filename.model import ClipEmbedder


class SimpleKindClassifier:
    """Binary classifier: angle vs color, trained on CLIP embeddings."""

    def __init__(self) -> None:
        self.encoder = LabelEncoder()
        self.model = LogisticRegression(max_iter=3000, class_weight="balanced", n_jobs=-1)
        self.fitted = False

    def fit(self, embeddings: np.ndarray, labels: list[str]) -> dict:
        encoded = self.encoder.fit_transform(labels)
        if len(set(labels)) < 2:
            self.model.fit(embeddings, encoded)
            self.fitted = True
            return {"train_accuracy": 1.0, "val_accuracy": 1.0, "num_classes": len(set(labels))}

        x_train, x_val, y_train, y_val = train_test_split(
            embeddings, encoded, test_size=0.2, random_state=42, stratify=encoded
        )
        self.model.fit(x_train, y_train)
        self.fitted = True
        return {
            "train_accuracy": float(self.model.score(x_train, y_train)),
            "val_accuracy": float(self.model.score(x_val, y_val)),
            "num_classes": len(self.encoder.classes_),
            "classes": list(self.encoder.classes_),
        }

    def predict_kind(self, embeddings: np.ndarray) -> tuple[list[str], list[float]]:
        if not self.fitted:
            return ["angle"] * len(embeddings), [0.0] * len(embeddings)
        probs = self.model.predict_proba(embeddings)
        idx = probs.argmax(axis=1)
        labels = [str(self.encoder.classes_[i]) for i in idx]
        conf = [float(probs[i, idx[i]]) for i in range(len(idx))]
        return labels, conf

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"encoder": self.encoder, "model": self.model, "fitted": self.fitted}, path)

    @classmethod
    def load(cls, path: Path) -> "SimpleKindClassifier":
        payload = joblib.load(path)
        obj = cls()
        obj.encoder = payload["encoder"]
        obj.model = payload["model"]
        obj.fitted = bool(payload.get("fitted", True))
        return obj


def default_simple_model_path(model_dir: Path) -> Path:
    return model_dir / "simple_kind_classifier.joblib"


def train_simple_kind_model(
    paths: list[str],
    labels: list[str],
    output_path: Path,
) -> dict:
    if len(paths) < 4:
        raise ValueError("學習樣本太少（至少 4 張，並同時有角度相與對色相更佳）")

    embedder = ClipEmbedder()
    embeddings, valid_paths = embedder.encode_paths(paths)
    path_to_label = dict(zip(paths, labels, strict=False))
    valid_labels = [path_to_label[p] for p in valid_paths]

    clf = SimpleKindClassifier()
    metrics = clf.fit(embeddings, valid_labels)
    clf.save(output_path)
    metrics.update(
        {
            "num_images": len(valid_paths),
            "model_file": str(output_path),
            "label_counts": {
                label: valid_labels.count(label) for label in sorted(set(valid_labels))
            },
        }
    )
    return metrics
