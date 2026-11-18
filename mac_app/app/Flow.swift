// Flow.swift (v18, 18.11.2026). Marko: "Please don't break the lines in the user interface ... Make this UI auto-wrap so it's
// not breaking things." Rule (MANTRA_MANIFEST modules/no-broken-words.md): a label or button is an unbreakable unit (one line,
// never truncated); when space is short WHOLE units move to the next row, never letters.
import SwiftUI

/// Lays its children out left to right and moves a whole child to the next row when it does not fit.
struct FlowLayout: Layout {
    var spacing: CGFloat = 4
    var rowSpacing: CGFloat = 2

    private func rows(_ subviews: Subviews, _ width: CGFloat) -> (frames: [CGRect], size: CGSize) {
        var frames: [CGRect] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowH: CGFloat = 0, maxW: CGFloat = 0
        for s in subviews {
            let sz = s.sizeThatFits(.unspecified)
            if x > 0 && x + sz.width > width { x = 0; y += rowH + rowSpacing; rowH = 0 }
            frames.append(CGRect(x: x, y: y, width: sz.width, height: sz.height))
            x += sz.width + spacing
            rowH = max(rowH, sz.height)
            maxW = max(maxW, x - spacing)
        }
        return (frames, CGSize(width: maxW, height: y + rowH))
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        rows(subviews, proposal.width ?? .infinity).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let r = rows(subviews, bounds.width)
        for (s, f) in zip(subviews, r.frames) {
            s.place(at: CGPoint(x: bounds.minX + f.minX, y: bounds.minY + f.minY), proposal: .unspecified)
        }
    }
}

extension View {
    /// One unbreakable unit: a single line, never cut, never broken inside a word.
    func unit() -> some View { self.lineLimit(1).fixedSize(horizontal: true, vertical: false) }
}

/// A draggable divider between two panes: drag to resize, double-click resets, the width is remembered.
struct SplitHandle: View {
    @Binding var width: Double
    var minW: Double
    var maxW: Double
    var reset: Double
    @State private var startW: Double? = nil
    var body: some View {
        Rectangle().fill(Ink.line).frame(width: 1)
            .overlay(
                Rectangle().fill(Color.clear).frame(width: 9).contentShape(Rectangle())
                    .onHover { inside in if inside { NSCursor.resizeLeftRight.push() } else { NSCursor.pop() } }
                    .gesture(DragGesture(minimumDistance: 1, coordinateSpace: .global)
                        .onChanged { g in
                            if startW == nil { startW = width }
                            width = min(maxW, max(minW, (startW ?? width) + Double(g.translation.width)))
                        }
                        .onEnded { _ in startW = nil })
                    .onTapGesture(count: 2) { width = reset }
                    .help("Drag to resize the list; double-click for the usual width")
                    .accessibilityElement()
                    .accessibilityLabel("Divider between the chat list and the chat")
                    .accessibilityValue("\(Int(width)) points")
                    .accessibilityAdjustableAction { d in
                        switch d {
                        case .increment: width = min(maxW, width + 20)
                        case .decrement: width = max(minW, width - 20)
                        @unknown default: break
                        }
                    }
            )
    }
}
