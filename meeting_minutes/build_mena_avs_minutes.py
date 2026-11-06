"""
Build the MENA AVS meeting minutes Word document from the existing transcript.

AWS (Bedrock/Comprehend) credentials were expired at generation time, so the
minutes text was authored directly from the transcript following the
meeting-minutes-workflow output structure. This script renders that content
plus the full transcript appendix into a formatted .docx.
"""

import os
from datetime import datetime

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUTPUT_DIR = r"c:\Users\stevekxs\Documents\Meeting Notes\meeting_minutes\output"
TRANSCRIPT_PATH = os.path.join(OUTPUT_DIR, "MENA_AVS_transcript.txt")
DOCX_PATH = os.path.join(OUTPUT_DIR, "MENA_AVS_meeting_minutes.docx")

TITLE = "Meeting Minutes - MENA AVS Discovery Call"

# ---- Structured minutes content (numbered-list lines use "N)" format) ----

OVERVIEW = (
    "Introductory discovery call between the RBS SPEG (Selling Partner Engagement and Growth) "
    "team, which manages Retail AVS vendors globally for Row and emerging stores, and the MENA "
    "AVS program leadership. RBS attendees were Steven and Shumei (Steven's manager), both based "
    "in Beijing and supporting the emerging-countries account management program. The MENA side "
    "was represented by Axel, who owns expansion, financials, and hiring for the MENA and Turkey "
    "AVS program. Purpose: RBS introduced its account management service model and explored "
    "whether it could support the MENA region, while MENA shared its current setup, cost "
    "structure, and constraints. The conversation was exploratory; both sides agreed to bring in "
    "additional stakeholders (Pedro Candiano on the MENA side) and exchange data for a proper "
    "evaluation."
)

KEY_TAKEAWAYS = [
    "RBS SPEG manages Row / emerging-store AVS vendors (tier 2 and tier 3, branded Spark or Light) end to end, and is expanding a similar model into emerging markets including the MENA region.",
    "This is the same RBS organization that previously supported EU Spark vendors, but the service and program have since evolved into a multi-program offering; leadership moved from Srinath to April (Shumei's skip), who now runs all rest-of-world and international emerging stores plus Japan.",
    "MENA AVS currently covers GCC (UAE, Saudi Arabia), Egypt, and Turkey (\"MENA TR\"), with occasional non-core support to South Africa. It runs two programs: AVS Core (onshore headcount) and AVS Essentials/Light (higher productivity, offshored brand specialists in Cairo).",
    "GCC Essentials is served by an offshore Cairo team fluent in Arabic (a GCC requirement); Egypt Essentials vendors lack a dedicated team and are handled by a blended core/essentials productivity target.",
    "MENA's top-down mandate from Seattle leadership is to reduce OPEX and increase productivity, not to grow operating margin (which is already healthy). The binding constraint is OPEX, not funding.",
    "Cost to serve: an Egypt brand specialist costs ~USD 20,000/year in salary and benefits and manages ~6 Essentials accounts, giving a cost to serve of ~USD 3,000 per account. Fully loaded (facilities, admin) the per-headcount cost rises to ~USD 40,000-42,000.",
    "MENA's key productivity goal is to raise Essentials accounts per headcount from ~6 to 10, which lowers cost to serve and reduces required headcount.",
    "MENA has hit its annual OPEX target and cannot hire additional headcount, so it currently cannot onboard more Essentials or Spark vendors due to capacity limits. RBS confirmed it faces the same hiring constraint.",
    "For any RBS proposal to land, the cost-to-serve incentive must be very clear, since Egypt is already a low-cost, high-bar talent source and even India headcount is more expensive than Egypt.",
    "RBS productivity benchmarks vary by service coverage: ~126 accounts target in Japan, ~125 in Australia, and 129 achieved this quarter for Australian direct-import (DI) AVS vendors.",
    "RBS raised that MENA retail revenue is growing ~40-50% year over year, but contribution margin and net PPM have been trending down from Q4 to Q2. MENA clarified the margin decline is driven by factors under its control (MOSE channel, regional conflict impact, and a mix shift to low-ASP items via quick commerce), not primarily OPEX.",
    "MENA AVS vendors are overwhelmingly global brands (~90-100%, e.g. Samsung, HP) but sold through local distributors holding local distribution rights; models vary by product family (soft lines use direct import; consumables/hard lines are more local via quick commerce).",
    "RBS offers account management from China and India hubs today, with the option to build local presence, and has proven cross-border mechanisms for international vendors selling into Egypt or Saudi Arabia from China, US, or the EU.",
]

ACTION_ITEMS = [
    (
        "Share the RBS AVS service menu and BS process/workflow details with MENA to enable a like-for-like productivity comparison.",
        "Steven (RBS)",
        "After the call",
        "\"could you please also share... the service menu for the BS, what process they are handling now and we can do another comparison\" -- productivity discussion",
    ),
    (
        "Run an OPEX comparison between the RBS (China/India) team and the Egypt team to identify cost-to-serve opportunities.",
        "Steven (RBS)",
        "TBD",
        "\"we can do the comparison between yinjir team and Egypt to see if we have any... rooms for the OPEX part\"",
    ),
    (
        "Involve Pedro Candiano (manager of the GCC Essentials team leads) on the thread so he can continue the conversation with RBS.",
        "Axel (MENA)",
        "After the call",
        "\"after the meeting, I will involve Pedro, so you can have... the conversation\"",
    ),
    (
        "Share the MENA AVS service menu and the outcome of the recent Egypt vendor-manager meeting on roles/responsibilities and service menu, to give RBS context on current discussions.",
        "Axel (MENA)",
        "After the call",
        "\"I will attach the service menu... there was a meeting with all the... vendor managers... on roles and responsibilities and the service menu\"",
    ),
    (
        "Collect additional model and OPEX-structure information (e.g., from UK) to determine the best operating location and cost structure for a potential MENA program.",
        "RBS team",
        "TBD",
        "\"we will definitely have more information maybe collecting from UK... to see... what's the best model and what's the best OPEX... structure\"",
    ),
    (
        "Schedule a follow-up call with more team members from both sides once initial data is exchanged.",
        "Steven (RBS)",
        "TBD",
        "\"I'll follow up with you and we'll maybe see another catch up... meeting with more team members\"",
    ),
]

DISCUSSION = [
    "RBS opened by positioning SPEG as the team that manages Retail AVS vendors globally, focused on tier 2 and tier 3 (Spark/Light) vendors, and expanding its model into emerging markets such as MENA. RBS offered a customized service menu tailored to each marketplace's specific pain points, prompted by MENA's earlier interest in the offer provided to Mexico.",
    "MENA gave detailed context on its setup. The region consolidated GCC (UAE, Saudi Arabia) with Egypt and Turkey into \"MENA TR,\" with occasional South Africa support. It runs AVS Core (onshore) and AVS Essentials/Light, the latter delivered by Arabic-fluent brand specialists offshored in Cairo who serve the expensive UAE and Saudi markets. Egypt's own Essentials vendors lack a dedicated team and are absorbed into a blended productivity target.",
    "Axel questioned whether RBS is the same organization that previously supported EU Spark vendors via an India-based team, where language and availability were pain points. RBS confirmed it is the same broader team (post-leadership change from Srinath to April) but with an evolved, multi-program service and hubs in China and India, plus proven cross-border support for global vendors.",
    "The core tension is economics. MENA's leadership mandate is to cut OPEX and lift productivity, not grow margin. With Egypt brand specialists at ~USD 20K/year managing ~6 accounts (~USD 3K cost to serve, ~USD 40-42K fully loaded), Axel flagged that any RBS proposal must present a clear cost advantage, which is hard because Egypt is already a low-cost, high-bar source. Both teams are currently blocked from hiring and cannot onboard more vendors.",
    "On performance, RBS noted MENA revenue growing 40-50% YoY while contribution margin and net PPM decline. MENA attributed the margin trend to controllable factors (MOSE channel, regional conflict, low-ASP mix via quick commerce) rather than OPEX. The parties agreed to compare service menus and productivity (RBS cited 125-129 accounts/HC benchmarks by coverage) to find improvement opportunities.",
    "The tone of the meeting was positive and collaborative, with both sides describing it as a good start and agreeing on concrete data exchange and stakeholder expansion as next steps.",
]

NEXT_STEPS = [
    "Both sides exchange service menus and productivity/OPEX data for a like-for-like comparison.",
    "MENA brings Pedro Candiano into the thread to lead the deeper GCC Essentials conversation.",
    "RBS gathers additional model/OPEX benchmarks (e.g., UK) and evaluates best-fit location and cost structure.",
    "Schedule a follow-up call with a broader group once initial data is shared.",
]


def add_numbered(doc, items):
    for i, text in enumerate(items, 1):
        doc.add_paragraph(f"{i}) {text}", style="List Number")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
        transcript = f.read().strip()

    doc = Document()
    normal = doc.styles["Normal"].font
    normal.name = "Calibri"
    normal.size = Pt(10)

    doc.add_heading(TITLE, level=0)
    date_para = doc.add_paragraph(f"Date: {datetime.now().strftime('%B %d, %Y')}")
    date_para.runs[0].font.size = Pt(10)
    date_para.runs[0].font.color.rgb = RGBColor(100, 100, 100)
    note = doc.add_paragraph(
        "Source: transcript of MENA AVS.mp3 (Whisper, small model). "
        "NLP appendix omitted (AWS Comprehend/Bedrock credentials unavailable at generation time)."
    )
    note.runs[0].font.size = Pt(8)
    note.runs[0].font.color.rgb = RGBColor(140, 140, 140)
    note.runs[0].font.italic = True

    doc.add_heading("1. Meeting Overview", level=1)
    doc.add_paragraph(OVERVIEW)

    doc.add_heading("2. Key Takeaways", level=1)
    add_numbered(doc, KEY_TAKEAWAYS)

    doc.add_heading("3. Action Items", level=1)
    for i, (desc, owner, eta, ref) in enumerate(ACTION_ITEMS, 1):
        p = doc.add_paragraph(style="List Number")
        p.add_run(f"{i}) {desc}")
        meta = doc.add_paragraph(f"Owner: {owner}. ETA: {eta}.")
        meta.paragraph_format.left_indent = Pt(24)
        meta.runs[0].font.size = Pt(9)
        refp = doc.add_paragraph(f"Reference: {ref}")
        refp.paragraph_format.left_indent = Pt(24)
        refp.runs[0].font.size = Pt(9)
        refp.runs[0].font.italic = True
        refp.runs[0].font.color.rgb = RGBColor(90, 90, 90)

    doc.add_heading("4. Discussion Summary", level=1)
    for para in DISCUSSION:
        doc.add_paragraph(para)

    doc.add_heading("5. Next Steps", level=1)
    add_numbered(doc, NEXT_STEPS)

    doc.add_page_break()
    doc.add_heading("Appendix: Full Transcript", level=1)
    tp = doc.add_paragraph(transcript)
    tp.runs[0].font.size = Pt(9)
    tp.runs[0].font.color.rgb = RGBColor(80, 80, 80)

    section = doc.sections[0]
    footer_para = section.footer.paragraphs[0]
    footer_para.text = "Amazon Confidential"
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_para.runs[0].font.size = Pt(8)
    footer_para.runs[0].font.color.rgb = RGBColor(150, 150, 150)

    doc.save(DOCX_PATH)
    print(f"Saved: {DOCX_PATH}")


if __name__ == "__main__":
    main()
