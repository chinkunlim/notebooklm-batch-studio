"""Generate a two-page sample biology lecture PDF for testing NotebookLM features.

Creates a structured sample PDF covering cell membrane structure and transport mechanisms
in `DATA_DIR/input/` so that NotebookLM upload, source selection, and artifact generation
can be verified with a realistic academic text.
"""

from __future__ import annotations

import logging
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from notebooklm_batch_studio.config.settings import AppConfig

logger = logging.getLogger(__name__)


def generate_cell_biology_pdf(output_path: Path) -> Path:
    """Create a two-page PDF on cell biology membrane transport.

    Args:
        output_path: Target filesystem path where the generated PDF will be saved.

    Returns:
        The resolved absolute path of the generated PDF file.
    """
    logger.info("Generating sample PDF at %s", output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=54,
        leftMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "LectureTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1A365D"),
        spaceAfter=12,
    )
    h2_style = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#2B6CB0"),
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=8,
    )

    story = []

    # Page 1: Structure & Passive Transport
    story.append(Paragraph("BIO101 Lecture 03: Cell Membrane Structure & Transport", title_style))
    story.append(Paragraph("Instructor: Department of Biological Sciences | Academic Year 2026", body_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph("1. The Fluid Mosaic Model", h2_style))
    story.append(
        Paragraph(
            "The plasma membrane defines the boundary of the cell and regulates molecular traffic. "
            "Proposed by Singer and Nicolson in 1972, the fluid mosaic model describes the membrane as a "
            "two-dimensional liquid of amphipathic phospholipid bilayers in which globular proteins are embedded. "
            "Phospholipids possess hydrophilic phosphate heads exposed to aqueous environments and hydrophobic "
            "fatty acid tails sequestered inside the bilayer core.",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "Membrane fluidity is modulated by temperature, fatty acid saturation (cis-double bonds introduce "
            "kinks preventing close packing), and cholesterol. Cholesterol functions as a bidirectional fluidity "
            "buffer: restraining phospholipid movement at high temperatures and preventing tight crystallization "
            "at low temperatures.",
            body_style,
        )
    )

    story.append(Paragraph("2. Passive Transport Mechanisms", h2_style))
    story.append(
        Paragraph(
            "Passive transport occurs spontaneously down an electrochemical gradient without direct metabolic energy "
            "(ATP) expenditure. It comprises three primary modalities:",
            body_style,
        )
    )

    table_data = [
        ["Transport Type", "Driver", "Protein Mediated", "Key Examples"],
        ["Simple Diffusion", "Concentration gradient", "No", "O2, CO2, small nonpolar lipids"],
        ["Osmosis", "Water potential gradient", "Aquaporins / Bilayer", "H2O across selectively permeable membrane"],
        ["Facilitated Diffusion", "Electrochemical gradient", "Yes (Channels / Carriers)", "Glucose (GLUT1), K+ voltage-gated channels"],
    ]
    t1 = Table(table_data, colWidths=[110, 130, 100, 160])
    t1.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1A202C")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E0")),
            ]
        )
    )
    story.append(t1)
    story.append(Spacer(1, 14))

    # Page Break to Page 2
    story.append(PageBreak())

    # Page 2: Active Transport & Bulk Transport
    story.append(Paragraph("3. Active Transport Mechanisms", h2_style))
    story.append(
        Paragraph(
            "Active transport moves solute particles against their thermodynamic concentration or electrochemical "
            "gradients. This process requires continuous cellular work and is categorized into primary and secondary "
            "active transport systems.",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "Primary active transport couples movement directly to the hydrolysis of ATP. The quintessential paradigm "
            "is the Sodium-Potassium Pump (Na+/K+-ATPase). In each enzymatic catalytic cycle, it consumes one molecule "
            "of ATP to export three Na+ ions out of the cell and import two K+ ions into the cytosol, establishing a net "
            "negative membrane potential inside (electrogenic pumping).",
            body_style,
        )
    )
    story.append(
        Paragraph(
            "Secondary active transport (cotransport) harnesses the potential energy stored in an established ionic "
            "gradient (most commonly the Na+ gradient generated by Na+/K+-ATPase) to drive the uphill translocation "
            "of another substrate. Examples include the Na+/Glucose Symporter (SGLT1 in intestinal epithelium) and the "
            "Na+/Ca2+ Antiporter in cardiac myocytes.",
            body_style,
        )
    )

    story.append(Paragraph("4. Bulk Transport: Endocytosis and Exocytosis", h2_style))
    story.append(
        Paragraph(
            "Macromolecules such as polysaccharides and polypeptides cross the membrane encapsulated in vesicles. "
            "Endocytosis includes phagocytosis ('cell eating'), pinocytosis ('cell drinking'), and receptor-mediated "
            "endocytosis mediated by clathrin-coated pits (e.g., LDL cholesterol uptake). Defective LDL receptors "
            "lead to hypercholesterolemia. Exocytosis involves secretory vesicle fusion with the plasma membrane, "
            "such as neurotransmitter release at synapses or insulin secretion by pancreatic beta cells.",
            body_style,
        )
    )

    story.append(Paragraph("Summary Review Questions for Study:", h2_style))
    story.append(
        Paragraph(
            "• Compare simple vs facilitated diffusion in terms of saturation kinetics (Vmax).<br/>"
            "• Explain why the Na+/K+ pump is considered electrogenic.<br/>"
            "• Predict how membrane fluidity changes if bacterial cultures are shifted from 37°C to 15°C.",
            body_style,
        )
    )

    doc.build(story)
    logger.info("Sample PDF generated successfully: %s", output_path)
    return output_path.resolve()


def main() -> None:
    """Entry point for standalone execution."""
    config = AppConfig()
    target_path = config.input_dir / "sample_cell_biology.pdf"
    result = generate_cell_biology_pdf(target_path)
    print(f"Sample PDF created at: {result}")


if __name__ == "__main__":
    main()
