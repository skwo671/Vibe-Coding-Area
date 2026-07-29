import SwiftUI

struct CardView: View {
    let card: Card
    var compact: Bool = false

    private var cardColor: Color {
        card.suit.isRed ? .red : .primary
    }

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: compact ? 10 : 14, style: .continuous)
                .fill(.white)
                .shadow(color: .black.opacity(0.12), radius: compact ? 4 : 8, y: compact ? 2 : 4)

            RoundedRectangle(cornerRadius: compact ? 10 : 14, style: .continuous)
                .strokeBorder(Color.black.opacity(0.08), lineWidth: 1)

            VStack(spacing: compact ? 2 : 6) {
                HStack {
                    VStack(alignment: .leading, spacing: 0) {
                        Text(card.rank.symbol)
                            .font(.system(size: compact ? 16 : 24, weight: .bold, design: .rounded))
                        Text(card.suit.rawValue)
                            .font(.system(size: compact ? 14 : 20))
                    }
                    Spacer()
                }

                Spacer()

                Text(card.suit.rawValue)
                    .font(.system(size: compact ? 28 : 44))

                Spacer()

                HStack {
                    Spacer()
                    VStack(alignment: .trailing, spacing: 0) {
                        Text(card.rank.symbol)
                            .font(.system(size: compact ? 16 : 24, weight: .bold, design: .rounded))
                        Text(card.suit.rawValue)
                            .font(.system(size: compact ? 14 : 20))
                    }
                    .rotationEffect(.degrees(180))
                }
            }
            .foregroundStyle(cardColor)
            .padding(compact ? 8 : 12)
        }
        .frame(width: compact ? 64 : 96, height: compact ? 90 : 136)
    }
}

#Preview {
    HStack {
        CardView(card: Card(suit: .hearts, rank: .ace))
        CardView(card: Card(suit: .spades, rank: .king), compact: true)
    }
    .padding()
    .background(Color.green.opacity(0.3))
}
