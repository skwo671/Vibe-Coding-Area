import Foundation

enum Suit: String, CaseIterable, Codable {
    case spades = "♠"
    case hearts = "♥"
    case diamonds = "♦"
    case clubs = "♣"

    var isRed: Bool {
        self == .hearts || self == .diamonds
    }
}

enum Rank: Int, CaseIterable, Codable {
    case ace = 1
    case two, three, four, five, six, seven, eight, nine, ten
    case jack, queen, king

    var symbol: String {
        switch self {
        case .ace: return "A"
        case .jack: return "J"
        case .queen: return "Q"
        case .king: return "K"
        default: return "\(rawValue)"
        }
    }
}

struct Card: Identifiable, Equatable, Codable {
    let id: UUID
    let suit: Suit
    let rank: Rank

    init(suit: Suit, rank: Rank, id: UUID = UUID()) {
        self.id = id
        self.suit = suit
        self.rank = rank
    }

    var displayName: String {
        "\(rank.symbol)\(suit.rawValue)"
    }
}
