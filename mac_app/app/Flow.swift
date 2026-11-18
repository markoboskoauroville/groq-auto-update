// Flow.swift (v18, 18.11.2026). Marko: "Please don't break the lines in the user interface ... Make this UI auto-wrap so it's
// not breaking things." Rule (MANTRA_MANIFEST modules/no-broken-words.md): a label or button is an unbreakable unit (one line,
// never truncated); when space is short WHOLE units move to the next row, never letters.
import SwiftUI

struct FlowRight: LayoutValueKey { static let defaultValue = false }
struct FlowPipe: LayoutValueKey { static let defaultValue = false }

/// Lays its children out left to right and moves a whole child to the next row when it does not fit.
/// A child marked .flowRight() sits at the right end of its row. A pipe (from .pipeGroup()) belongs to the child AFTER it:
/// they wrap together, and a pipe that would start a row is hidden (placed outside, clipped), so no separator ever dangles.
struct FlowLayout: Layout {
    var spacing: CGFloat = 4
    var rowSpacing: CGFloat = 2
    var pipeGap: CGFloat = 6

    private func rows(_ subviews: Subviews, _ width: CGFloat) -> (frames: [CGRect], size: CGSize) {
        var frames = [CGRect](repeating: .zero, count: subviews.count)
        var base = [CGFloat](repeating: 0, count: subviews.count)       // each child's text baseline (v22: rows sit on ONE baseline)
        for (i, s) in subviews.enumerated() {
            let d = s.dimensions(in: .unspecified)
            base[i] = d[.firstTextBaseline]
        }
        var x: CGFloat = 0, maxW: CGFloat = 0
        var rows: [[Int]] = [[]]
        var rowStart = 0
        func closeRow(_ end: Int) {
            guard width.isFinite, end > rowStart else { return }
            var first = end
            while first > rowStart && subviews[first - 1][FlowRight.self] { first -= 1 }
            if first < end {
                let shift = width - frames[end - 1].maxX
                if shift > 0 { for i in first..<end { frames[i].origin.x += shift } }
            }
        }
        var pipeIdx: Int? = nil
        for (idx, s) in subviews.enumerated() {
            if s[FlowPipe.self] { pipeIdx = idx; continue }
            let sz = s.sizeThatFits(.unspecified)
            let pw = pipeIdx.map { subviews[$0].sizeThatFits(.unspecified).width + pipeGap } ?? 0
            let start = pipeIdx ?? idx
            if x > 0 && x + pw + sz.width > width {
                closeRow(start); rowStart = start; x = 0; rows.append([])
            }
            var lead: CGFloat = 0
            if let p = pipeIdx {
                let ps = subviews[p].sizeThatFits(.unspecified)
                if x > 0 {
                    frames[p] = CGRect(x: x, y: 0, width: ps.width, height: ps.height)
                    lead = pw
                    rows[rows.count - 1].append(p)
                } else {
                    frames[p] = CGRect(x: -10000, y: 0, width: ps.width, height: ps.height)   // would start a row: hidden
                }
            }
            frames[idx] = CGRect(x: x + lead, y: 0, width: sz.width, height: sz.height)
            rows[rows.count - 1].append(idx)
            x += lead + sz.width + spacing
            maxW = max(maxW, x - spacing)
            pipeIdx = nil
        }
        closeRow(subviews.count)
        // vertical: every row on its own common baseline
        var y: CGFloat = 0
        for r in rows where !r.isEmpty {
            let b = r.map { base[$0] }.max() ?? 0
            var h: CGFloat = 0
            for m in r {
                frames[m].origin.y = y + b - base[m]
                h = max(h, b - base[m] + frames[m].height)
            }
            y += h + rowSpacing
        }
        return (frames, CGSize(width: width.isFinite ? max(maxW, width) : maxW, height: max(0, y - rowSpacing)))
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
    /// In a FlowLayout: sit at the right end of the row.
    func flowRight() -> some View { layoutValue(key: FlowRight.self, value: true) }
    /// A logical group: a dim pipe BEFORE it, belonging to it, and the whole group one unbreakable unit.
    func pipeGroup() -> some View {
        Group {
            Text("|").foregroundStyle(Ink.dim).unit().layoutValue(key: FlowPipe.self, value: true)
            self
        }
    }
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
