import Foundation

struct Deck {
    private(set) var cards: [Card]

    init(includeJokers: Bool = false) {
        var deck = Suit.allCases.flatMap { suit in
            Rank.allCases.map { rank in
                Card(suit: suit, rank: rank)
            }
        }

        if includeJokers {
            // Reserved for future joker support.
        }

        cards = deck
    }

    mutating func shuffle() {
        cards.shuffle()
    }

    @discardableResult
    mutating func draw() -> Card? {
        guard !cards.isEmpty else { return nil }
        return cards.removeFirst()
    }

    mutating func draw(count: Int) -> [Card] {
        let drawCount = min(count, cards.count)
        let drawn = Array(cards.prefix(drawCount))
        cards.removeFirst(drawCount)
        return drawn
    }

    mutating func reset(includeJokers: Bool = false) {
        self = Deck(includeJokers: includeJokers)
        shuffle()
    }

    var remainingCount: Int {
        cards.count
    }
}
