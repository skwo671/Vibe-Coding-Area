import Foundation
import SwiftUI

@MainActor
final class DeckViewModel: ObservableObject {
    @Published private(set) var deck = Deck()
    @Published private(set) var drawnCards: [Card] = []
    @Published private(set) var lastDrawnCard: Card?
    @Published var showEmptyDeckAlert = false

    var remainingCount: Int {
        deck.remainingCount
    }

    init() {
        deck.shuffle()
    }

    func drawCard() {
        guard let card = deck.draw() else {
            showEmptyDeckAlert = true
            return
        }

        withAnimation(.spring(response: 0.45, dampingFraction: 0.78)) {
            lastDrawnCard = card
            drawnCards.insert(card, at: 0)
        }
    }

    func drawHand(count: Int) {
        let cards = deck.draw(count: count)
        guard !cards.isEmpty else {
            showEmptyDeckAlert = true
            return
        }

        withAnimation(.spring(response: 0.45, dampingFraction: 0.78)) {
            lastDrawnCard = cards.last
            drawnCards.insert(contentsOf: cards.reversed(), at: 0)
        }
    }

    func shuffleDeck() {
        withAnimation(.easeInOut(duration: 0.25)) {
            deck.shuffle()
        }
    }

    func resetDeck() {
        withAnimation(.easeInOut(duration: 0.3)) {
            deck.reset()
            drawnCards.removeAll()
            lastDrawnCard = nil
        }
    }

    func clearDrawnCards() {
        withAnimation(.easeInOut(duration: 0.25)) {
            drawnCards.removeAll()
            lastDrawnCard = nil
        }
    }
}
