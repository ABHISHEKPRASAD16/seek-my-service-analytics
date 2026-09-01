/*
 * Build the submittable Word document from docs/PROJECT_REPORT.md.
 *
 * Produces an academic-format report: A4, Times New Roman 12pt, 1.5 line
 * spacing, justified body text, a title page, an auto-updating table of
 * contents, numbered pages, and a signed declaration.
 *
 * Run:  node build/build_report.js
 */

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  PageBreak, Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  TableOfContents, Footer, Header, PageNumber, LevelFormat, convertInchesToTwip,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const SOURCE = path.join(ROOT, "docs", "PROJECT_REPORT.md");
const OUTPUT = path.join(ROOT, "build", "Seek_My_Service_Project_Report.docx");

const AUTHOR = "Abhishek Prasad";
const SUBMISSION_DATE = "01.10.2026";
const FONT = "Times New Roman";

// ---------------------------------------------------------------------------
// Inline markdown: **bold**, *italic*, `code`
// ---------------------------------------------------------------------------
function runs(text, base = {}) {
  const out = [];
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let m;
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) {
      out.push(new TextRun({ text: text.slice(last, m.index), font: FONT, size: 24, ...base }));
    }
    const token = m[0];
    if (token.startsWith("**")) {
      out.push(new TextRun({ text: token.slice(2, -2), bold: true, font: FONT, size: 24, ...base }));
    } else if (token.startsWith("`")) {
      out.push(new TextRun({ text: token.slice(1, -1), font: "Consolas", size: 21, ...base }));
    } else {
      out.push(new TextRun({ text: token.slice(1, -1), italics: true, font: FONT, size: 24, ...base }));
    }
    last = m.index + token.length;
  }
  if (last < text.length) {
    out.push(new TextRun({ text: text.slice(last), font: FONT, size: 24, ...base }));
  }
  return out.length ? out : [new TextRun({ text: "", font: FONT, size: 24 })];
}

const body = (text, opts = {}) =>
  new Paragraph({
    children: runs(text),
    alignment: AlignmentType.JUSTIFIED,
    spacing: { line: 360, after: 160 },
    ...opts,
  });

// ---------------------------------------------------------------------------
// Tables
// ---------------------------------------------------------------------------
const CONTENT_WIDTH = 9360; // A4 minus 1" margins, in DXA

function splitRow(line) {
  return line.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
}

function buildTable(lines) {
  const header = splitRow(lines[0]);
  const dataLines = lines.slice(2).filter((l) => l.trim().startsWith("|"));
  const cols = header.length;
  const colWidth = Math.floor(CONTENT_WIDTH / cols);
  const widths = Array(cols).fill(colWidth);
  widths[cols - 1] = CONTENT_WIDTH - colWidth * (cols - 1);

  const cell = (text, isHeader, width) =>
    new TableCell({
      width: { size: width, type: WidthType.DXA },
      shading: isHeader
        ? { type: ShadingType.CLEAR, fill: "E8EDF2" }
        : undefined,
      margins: { top: 60, bottom: 60, left: 100, right: 100 },
      children: [
        new Paragraph({
          children: runs(text.replace(/<br\/?>/g, " "), { bold: isHeader || undefined, size: 21 }),
          spacing: { line: 240, after: 0 },
        }),
      ],
    });

  const rows = [
    new TableRow({
      tableHeader: true,
      children: header.map((h, i) => cell(h, true, widths[i])),
    }),
    ...dataLines.map((line) => {
      const cells = splitRow(line);
      while (cells.length < cols) cells.push("");
      return new TableRow({
        children: cells.slice(0, cols).map((c, i) => cell(c, false, widths[i])),
      });
    }),
  ];

  return new Table({
    columnWidths: widths,
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    rows,
    borders: {
      top: { style: BorderStyle.SINGLE, size: 4, color: "9AA5B1" },
      bottom: { style: BorderStyle.SINGLE, size: 4, color: "9AA5B1" },
      left: { style: BorderStyle.SINGLE, size: 4, color: "9AA5B1" },
      right: { style: BorderStyle.SINGLE, size: 4, color: "9AA5B1" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "C7CFD8" },
      insideVertical: { style: BorderStyle.SINGLE, size: 2, color: "C7CFD8" },
    },
  });
}

// ---------------------------------------------------------------------------
// Markdown -> docx elements
// ---------------------------------------------------------------------------
function convert(markdown) {
  const lines = markdown.split(/\r?\n/);
  const out = [];
  let i = 0;

  // Everything before the Table of Contents heading is replaced by our own
  // title page and front matter, so skip to Acknowledgement.
  const start = lines.findIndex((l) => l.startsWith("## Acknowledgement"));
  i = start >= 0 ? start : 0;

  let skipToc = false;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    // The source's manual TOC listing is replaced by a generated field.
    if (/^## Table of Contents/.test(trimmed)) { skipToc = true; i++; continue; }
    if (skipToc) {
      if (/^## /.test(trimmed)) { skipToc = false; } else { i++; continue; }
    }

    if (!trimmed) { i++; continue; }

    // Horizontal rule -> ignored (we control page breaks explicitly)
    if (/^---+$/.test(trimmed)) { i++; continue; }

    // Tables
    if (trimmed.startsWith("|")) {
      const block = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) { block.push(lines[i].trim()); i++; }
      if (block.length >= 2) {
        out.push(buildTable(block));
        out.push(new Paragraph({ text: "", spacing: { after: 200 } }));
      }
      continue;
    }

    // Headings
    const h = trimmed.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      const depth = h[1].length;
      const text = h[2].replace(/\*\*/g, "").trim();

      // Each chapter starts on a fresh page.
      if (/^Chapter \d|^References$|^Appendix \d/.test(text)) {
        out.push(new Paragraph({ children: [new PageBreak()] }));
      }

      const level = depth === 1 ? HeadingLevel.HEADING_1
        : depth === 2 ? HeadingLevel.HEADING_2
        : depth === 3 ? HeadingLevel.HEADING_3
        : HeadingLevel.HEADING_4;

      out.push(new Paragraph({
        heading: level,
        spacing: { before: depth === 1 ? 240 : 280, after: 160 },
        children: [new TextRun({
          text,
          font: FONT,
          bold: true,
          size: depth === 1 ? 32 : depth === 2 ? 27 : 25,
          color: "1F2933",
        })],
      }));
      i++;
      continue;
    }

    // Block quote
    if (trimmed.startsWith(">")) {
      const block = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) {
        block.push(lines[i].trim().replace(/^>\s?/, "")); i++;
      }
      const text = block.filter((l) => l.trim() && !l.trim().startsWith("|")).join(" ").trim();
      if (text) {
        out.push(new Paragraph({
          children: runs(text.replace(/^#+\s*/, "")),
          alignment: AlignmentType.JUSTIFIED,
          spacing: { line: 320, after: 200, before: 120 },
          indent: { left: convertInchesToTwip(0.4) },
          border: { left: { style: BorderStyle.SINGLE, size: 12, color: "2A6FB5", space: 12 } },
        }));
      }
      continue;
    }

    // Bullet list
    if (/^[-*]\s+/.test(trimmed)) {
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        out.push(new Paragraph({
          children: runs(lines[i].trim().replace(/^[-*]\s+/, "")),
          numbering: { reference: "bullets", level: 0 },
          alignment: AlignmentType.JUSTIFIED,
          spacing: { line: 320, after: 80 },
        }));
        i++;
      }
      out.push(new Paragraph({ text: "", spacing: { after: 100 } }));
      continue;
    }

    // Numbered list
    if (/^\d+\.\s+/.test(trimmed)) {
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        out.push(new Paragraph({
          children: runs(lines[i].trim().replace(/^\d+\.\s+/, "")),
          numbering: { reference: "numbers", level: 0 },
          alignment: AlignmentType.JUSTIFIED,
          spacing: { line: 320, after: 80 },
        }));
        i++;
      }
      out.push(new Paragraph({ text: "", spacing: { after: 100 } }));
      continue;
    }

    // Ordinary paragraph — join continuation lines
    const para = [trimmed];
    i++;
    while (i < lines.length) {
      const nxt = lines[i].trim();
      if (!nxt || /^[-*#>|]/.test(nxt) || /^\d+\.\s/.test(nxt) || /^---+$/.test(nxt)) break;
      para.push(nxt); i++;
    }
    out.push(body(para.join(" ")));
  }

  return out;
}

// ---------------------------------------------------------------------------
// Front matter
// ---------------------------------------------------------------------------
const centered = (text, opts = {}) =>
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: opts.after || 200 },
    children: [new TextRun({
      text, font: FONT, size: opts.size || 24,
      bold: opts.bold || false, italics: opts.italics || false,
      color: opts.color || "000000",
    })],
  });

function titlePage() {
  return [
    new Paragraph({ text: "", spacing: { after: 1400 } }),
    centered("Early Detection of Silent Machine Learning Pipeline Failure", { size: 36, bold: true, after: 120 }),
    centered("Through Operational Monitoring", { size: 36, bold: true, after: 120 }),
    centered("A Marketplace Analytics Case Study", { size: 28, italics: true, after: 1000 }),
    centered("Master of Science / Informatik", { size: 26, after: 120 }),
    centered("IU Internationale Hochschule", { size: 26, after: 60 }),
    centered("Berlin, Germany", { size: 26, after: 1000 }),
    centered(`Student Name: ${AUTHOR}`, { size: 26, after: 100 }),
    centered("Student ID: 102301095", { size: 26, after: 100 }),
    centered(`Submission Date: ${SUBMISSION_DATE}`, { size: 26, after: 100 }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

function tocPage() {
  return [
    new Paragraph({
      heading: HeadingLevel.HEADING_1,
      spacing: { after: 240 },
      children: [new TextRun({ text: "Table of Contents", font: FONT, bold: true, size: 32 })],
    }),
    new TableOfContents("Table of Contents", {
      hyperlink: true,
      headingStyleRange: "1-3",
    }),
    new Paragraph({
      spacing: { before: 240 },
      children: [new TextRun({
        text: "To populate this table in Word: select it, then press F9 and choose "
            + "\"Update entire table\".",
        font: FONT, size: 20, italics: true, color: "5A6673",
      })],
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

function declarationPage() {
  return [
    new Paragraph({ children: [new PageBreak()] }),
    new Paragraph({
      heading: HeadingLevel.HEADING_1,
      spacing: { after: 240 },
      children: [new TextRun({ text: "Declaration of Authenticity", font: FONT, bold: true, size: 32 })],
    }),
    body("I hereby declare that this work is my own and that all sources used have been "
       + "acknowledged. The artefact described in this report was designed, implemented and "
       + "evaluated by me for the purpose of this study."),
    body("The dataset analysed is synthetic and was generated by the programs contained in the "
       + "accompanying repository. It does not represent any real organisation, individual or "
       + "transaction, and this is stated in the artefact's documentation and user interface."),
    body("I further declare that this work has not been submitted for any other degree or "
       + "qualification."),
    new Paragraph({ text: "", spacing: { after: 700 } }),
    new Paragraph({
      spacing: { after: 60 },
      children: [new TextRun({ text: AUTHOR, font: "Segoe Script", size: 32, color: "1F3A63" })],
    }),
    new Paragraph({
      border: { top: { style: BorderStyle.SINGLE, size: 6, color: "000000", space: 4 } },
      spacing: { after: 80 },
      children: [new TextRun({ text: "", size: 4 })],
    }),
    new Paragraph({
      spacing: { after: 60 },
      children: [new TextRun({ text: AUTHOR, font: FONT, size: 24, bold: true })],
    }),
    new Paragraph({
      children: [new TextRun({ text: `Berlin, ${SUBMISSION_DATE}`, font: FONT, size: 24 })],
    }),
  ];
}

// ---------------------------------------------------------------------------
// Assemble
// ---------------------------------------------------------------------------
const markdown = fs.readFileSync(SOURCE, "utf8");

const doc = new Document({
  creator: AUTHOR,
  title: "Early Detection of Silent Machine Learning Pipeline Failure Through Operational Monitoring",
  description: "MSc Informatik project report, IU Internationale Hochschule",
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: "•",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 260 } } },
        }],
      },
      {
        reference: "numbers",
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: "%1.",
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 260 } } },
        }],
      },
    ],
  },
  sections: [{
    properties: {
      // A distinct first page, so the title page carries no running header or
      // page number. Convention for an academic submission, and the first
      // export got this wrong.
      titlePage: true,
      page: {
        margin: {
          top: convertInchesToTwip(1), bottom: convertInchesToTwip(1),
          left: convertInchesToTwip(1.2), right: convertInchesToTwip(1),
        },
      },
    },
    headers: {
      first: new Header({ children: [new Paragraph({ text: "" })] }),
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "C7CFD8", space: 6 } },
          children: [new TextRun({
            text: "Seek My Service — MSc Informatik Project Report",
            font: FONT, size: 18, color: "5A6673",
          })],
        })],
      }),
    },
    footers: {
      first: new Footer({ children: [new Paragraph({ text: "" })] }),
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 20 })],
        })],
      }),
    },
    children: [
      ...titlePage(),
      ...tocPage(),
      ...convert(markdown),
      ...declarationPage(),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUTPUT, buf);
  const kb = (buf.length / 1024).toFixed(0);
  console.log(`written: ${OUTPUT}`);
  console.log(`size   : ${kb} KB`);
});
