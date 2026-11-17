// Markdown.swift: Claude's and Queen's answers as real Markdown (CAPI tab, 17.11.2026): headings, bullets, numbered lists,
// fenced code, tables and bold/italic/code inline, no raw ** or backticks. One module: Bubble (every chat) uses it.
import SwiftUI

enum MDBlock {
    case heading(Int, String)
    case para(String)
    case item(String, String)      // marker ("•" or "1."), text
    case code(String)
    case table([[String]])
}

enum Markdown {
    static func parse(_ s: String) -> [MDBlock] {
        var out: [MDBlock] = []
        var para: [String] = []
        var code: [String] = []
        var inCode = false
        var rows: [[String]] = []
        func flushPara() { if !para.isEmpty { out.append(.para(para.joined(separator: "\n"))); para = [] } }
        func flushRows() { if !rows.isEmpty { out.append(.table(rows)); rows = [] } }
        for raw in s.components(separatedBy: "\n") {
            let t = raw.trimmingCharacters(in: .whitespaces)
            if t.hasPrefix("```") {
                if inCode { out.append(.code(code.joined(separator: "\n"))); code = []; inCode = false }
                else { flushPara(); flushRows(); inCode = true }
                continue
            }
            if inCode { code.append(raw); continue }
            if t.hasPrefix("|") {
                flushPara()
                let cells = t.split(separator: "|", omittingEmptySubsequences: false).dropFirst().dropLast()
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                if !cells.isEmpty && cells.allSatisfy({ $0.allSatisfy { "-: ".contains($0) } && !$0.isEmpty }) { continue }
                rows.append(Array(cells))
                continue
            }
            flushRows()
            if t.isEmpty { flushPara(); continue }
            if t.hasPrefix("#") {
                flushPara()
                let n = t.prefix(while: { $0 == "#" }).count
                out.append(.heading(min(n, 3), String(t.dropFirst(n)).trimmingCharacters(in: .whitespaces)))
            } else if t.hasPrefix("- ") || t.hasPrefix("* ") || t.hasPrefix("+ ") {
                flushPara(); out.append(.item("•", String(t.dropFirst(2))))
            } else if let r = t.range(of: #"^\d+\.\s"#, options: .regularExpression) {
                flushPara(); out.append(.item(String(t[r]).trimmingCharacters(in: .whitespaces), String(t[r.upperBound...])))
            } else {
                para.append(t)
            }
        }
        if inCode { out.append(.code(code.joined(separator: "\n"))) }
        flushPara(); flushRows()
        return out
    }

    static func inline(_ s: String) -> AttributedString {
        let opts = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: s, options: opts)) ?? AttributedString(s)
    }
}

struct MarkdownView: View {
    let text: String
    var body: some View {
        let blocks = Markdown.parse(text)
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, b in block(b) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private func block(_ b: MDBlock) -> some View {
        switch b {
        case .heading(let n, let t):
            Text(Markdown.inline(t)).font(.system(size: n == 1 ? 18 : (n == 2 ? 16 : 15), weight: .bold))
                .foregroundStyle(Ink.text).fixedSize(horizontal: false, vertical: true)
        case .para(let t):
            Text(Markdown.inline(t)).font(.system(size: 14)).foregroundStyle(Ink.text)
                .fixedSize(horizontal: false, vertical: true)
        case .item(let m, let t):
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(m).font(.system(size: 14, design: .monospaced)).foregroundStyle(Ink.dim).frame(width: 22, alignment: .trailing)
                Text(Markdown.inline(t)).font(.system(size: 14)).foregroundStyle(Ink.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        case .code(let c):
            Text(c).font(.system(size: 12, design: .monospaced)).foregroundStyle(Ink.text)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
                .background(RoundedRectangle(cornerRadius: 5).fill(Color.black.opacity(0.35)))
        case .table(let rows):
            Grid(alignment: .topLeading, horizontalSpacing: 14, verticalSpacing: 4) {
                ForEach(Array(rows.enumerated()), id: \.offset) { i, r in
                    GridRow {
                        ForEach(Array(r.enumerated()), id: \.offset) { _, c in
                            Text(Markdown.inline(c)).font(.system(size: 13, weight: i == 0 ? .bold : .regular))
                                .foregroundStyle(i == 0 ? Ink.dim : Ink.text)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            .padding(8)
            .background(RoundedRectangle(cornerRadius: 5).fill(Ink.panel))
        }
    }
}
