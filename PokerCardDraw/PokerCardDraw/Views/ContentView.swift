import SwiftUI

struct ContentView: View {
    @StateObject private var viewModel = DeckViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                LinearGradient(
                    colors: [
                        Color(red: 0.08, green: 0.42, blue: 0.24),
                        Color(red: 0.04, green: 0.28, blue: 0.16)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                .ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 24) {
                        deckStatusSection
                        lastCardSection
                        actionButtonsSection
                        drawnCardsSection
                    }
                    .padding()
                }
            }
            .navigationTitle("撲克牌抽牌")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            .alert("牌組已抽完", isPresented: $viewModel.showEmptyDeckAlert) {
                Button("重新洗牌") {
                    viewModel.resetDeck()
                }
                Button("取消", role: .cancel) {}
            } message: {
                Text("請重新洗牌後再繼續抽牌。")
            }
        }
    }

    private var deckStatusSection: some View {
        HStack {
            Label("剩餘 \(viewModel.remainingCount) 張", systemImage: "rectangle.stack.fill")
            Spacer()
            Label("已抽 \(viewModel.drawnCards.count) 張", systemImage: "hand.raised.fill")
        }
        .font(.subheadline.weight(.semibold))
        .foregroundStyle(.white.opacity(0.9))
        .padding()
        .background(.white.opacity(0.12), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    @ViewBuilder
    private var lastCardSection: some View {
        VStack(spacing: 12) {
            Text("最新抽到的牌")
                .font(.headline)
                .foregroundStyle(.white.opacity(0.85))

            if let card = viewModel.lastDrawnCard {
                CardView(card: card)
                    .transition(.asymmetric(
                        insertion: .scale(scale: 0.6).combined(with: .opacity),
                        removal: .opacity
                    ))
                    .id(card.id)
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(.white.opacity(0.08))
                        .frame(width: 96, height: 136)
                        .overlay {
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .strokeBorder(.white.opacity(0.2), style: StrokeStyle(lineWidth: 2, dash: [8]))
                        }

                    VStack(spacing: 8) {
                        Image(systemName: "questionmark")
                            .font(.title)
                        Text("按下方按鈕抽牌")
                            .font(.caption)
                    }
                    .foregroundStyle(.white.opacity(0.6))
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
    }

    private var actionButtonsSection: some View {
        VStack(spacing: 12) {
            Button {
                viewModel.drawCard()
            } label: {
                Label("抽一張牌", systemImage: "plus.circle.fill")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(PrimaryButtonStyle())

            HStack(spacing: 12) {
                Button("抽 5 張") {
                    viewModel.drawHand(count: 5)
                }
                .buttonStyle(SecondaryButtonStyle())

                Button("抽 2 張") {
                    viewModel.drawHand(count: 2)
                }
                .buttonStyle(SecondaryButtonStyle())
            }

            HStack(spacing: 12) {
                Button("洗牌") {
                    viewModel.shuffleDeck()
                }
                .buttonStyle(SecondaryButtonStyle())

                Button("重置") {
                    viewModel.resetDeck()
                }
                .buttonStyle(SecondaryButtonStyle())
            }
        }
    }

    @ViewBuilder
    private var drawnCardsSection: some View {
        if !viewModel.drawnCards.isEmpty {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("已抽到的牌")
                        .font(.headline)
                        .foregroundStyle(.white)

                    Spacer()

                    Button("清除記錄") {
                        viewModel.clearDrawnCards()
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.8))
                }

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 72), spacing: 12)], spacing: 12) {
                    ForEach(viewModel.drawnCards) { card in
                        CardView(card: card, compact: true)
                    }
                }
            }
            .padding()
            .background(.white.opacity(0.1), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        }
    }
}

struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .padding(.vertical, 14)
            .background(Color.white)
            .foregroundStyle(Color(red: 0.08, green: 0.42, blue: 0.24))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(.white.opacity(0.14))
            .foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .strokeBorder(.white.opacity(0.18), lineWidth: 1)
            }
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
    }
}

#Preview {
    ContentView()
}
