"""
One-time script to create the Video #005 draft JSON from the pre-written final script.
Run: python create_video005_draft.py
Topic: Prediction 5 — The Iran war ends the US-led unipolar moment
"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DRAFTS_DIR = ROOT / "outputs" / "drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

segments = [
    {
        "text": "The United States is burning two billion dollars a day on a war Congress never authorized. Against a country whose strait controls twenty percent of the world's oil supply. And its own military just admitted it cannot keep that strait open.",
        "footage_keyword": "warship aircraft carrier dark ocean dramatic aerial",
        "footage_mood": "ominous",
        "source_type": "stock",
        "search_query": "warship aircraft carrier dark ocean dramatic aerial",
        "highlight_phrase": "TWO BILLION DOLLARS A DAY",
    },
    {
        "text": "That is not a crisis. That is a structural collapse — in slow motion. And one analyst called it months before the first bomb dropped.",
        "footage_keyword": "crumbling empire stone structure collapse slow motion dramatic",
        "footage_mood": "dramatic",
        "source_type": "dalle",
        "search_query": "ancient stone empire structure crumbling dramatic dark sky",
        "highlight_phrase": "STRUCTURAL COLLAPSE IN SLOW MOTION",
    },
    {
        "text": "In the last video, we watched Russia quietly exploit America's distraction. Prediction 4 — Russia and China move while the US bleeds in Iran — went from Pending to Active.",
        "footage_keyword": "chess board dark strategy pieces close up dramatic",
        "footage_mood": "tense",
        "source_type": "stock",
        "search_query": "chess board dark dramatic strategy pieces close up",
        "highlight_phrase": "PENDING TO ACTIVE",
    },
    {
        "text": "Today is Prediction 5. The one Prof. Jiang Xueqin called the end game. His exact claim: this war will not just drain American resources. It will mark the end of the US-led unipolar moment — the thirty-year era in which one country set the rules for everyone else.",
        "footage_keyword": "globe dark spinning dramatic cinematic world map geopolitical",
        "footage_mood": "dramatic",
        "source_type": "stock",
        "search_query": "globe spinning dark cinematic dramatic geopolitical",
        "highlight_phrase": "THE END GAME",
    },
    {
        "text": "Jiang's framework is not commentary. It is psychohistory combined with game theory. He maps the payoff structures rational actors face under structural pressure — then shows what they are forced to do. Not what they want to do. What the math makes them do.",
        "footage_keyword": "ancient world map parchment empire borders payoff matrix",
        "footage_mood": "analytical",
        "source_type": "dalle",
        "search_query": "ancient parchment world map empire borders overlaid dark atmospheric",
        "highlight_phrase": "WHAT THE MATH MAKES THEM DO",
    },
    {
        "text": "He was right about the strikes. Right about the attrition. Right about Russia moving. Three for three. So when he says Prediction 5 is not a question of if — only when — that is worth taking seriously. Here are the three historical parallels he builds the case on.",
        "footage_keyword": "scorecard tally marks three confirmed dark dramatic",
        "footage_mood": "analytical",
        "source_type": "motion_graphic",
        "search_query": "prediction scorecard three confirmed tally marks",
        "highlight_phrase": "THREE FOR THREE",
    },
    {
        "text": "First parallel: Britain after Suez, 1956. Britain invaded Egypt to retake the Suez Canal. The military operation succeeded. Then the United States — fearing Soviet escalation — forced Britain to withdraw.",
        "footage_keyword": "Suez Canal Egypt historical map 1956 British forces",
        "footage_mood": "dramatic",
        "source_type": "wikimedia",
        "search_query": "Suez Crisis 1956 British forces Egypt",
        "highlight_phrase": "FIRST PARALLEL",
    },
    {
        "text": "In one week, the world learned Britain could not act without American permission. The British Empire did not end with a battle. It ended with an invoice it couldn't pay and an ally that wouldn't back it. America today is Britain in 1956 — except there is no larger power forcing it to stop. That is what makes this more dangerous, not less.",
        "footage_keyword": "British Empire flag decline historical dramatic dark",
        "footage_mood": "ominous",
        "source_type": "dalle",
        "search_query": "British Empire flag faded declining dramatic dark atmospheric parchment",
        "highlight_phrase": "AN INVOICE IT COULDN'T PAY",
    },
    {
        "text": "Second parallel: America after Vietnam. Vietnam cost 58,000 lives. Over 800 billion in today's dollars. And something harder to quantify — the credibility that comes from winning.",
        "footage_keyword": "Vietnam war jungle soldiers dramatic dark historical",
        "footage_mood": "dramatic",
        "source_type": "wikimedia",
        "search_query": "Vietnam War soldiers jungle",
        "highlight_phrase": "SECOND PARALLEL",
    },
    {
        "text": "But the deeper damage was structural. While America bled in Southeast Asia, Nixon was forced to take the dollar off gold. OPEC formed. The Soviet Union expanded. Every adversary read the same signal: America can be outlasted.",
        "footage_keyword": "US dollar bill dramatic dark crumpling inflation crisis",
        "footage_mood": "ominous",
        "source_type": "stock",
        "search_query": "US dollar bill dark dramatic inflation currency crisis",
        "highlight_phrase": "AMERICA CAN BE OUTLASTED",
    },
    {
        "text": "Now run that forward. Russia is giving Iran real-time satellite intelligence on US warship locations. China just raised its defense budget seven percent and is positioning as the post-war mediator. They are not watching. They are moving into the space.",
        "footage_keyword": "satellite dark orbit intelligence surveillance dramatic cinematic",
        "footage_mood": "ominous",
        "source_type": "stock",
        "search_query": "satellite orbit dark dramatic surveillance intelligence cinematic",
        "highlight_phrase": "MOVING INTO THE SPACE",
    },
    {
        "text": "Third parallel: Rome at the frontier. Rome's decline did not begin at the capital. It began at the edges — too many frontiers, legions stretched too thin, resources flowing away from the center faster than they could be replaced.",
        "footage_keyword": "Roman Colosseum ruins dramatic sky ancient empire",
        "footage_mood": "dramatic",
        "source_type": "wikimedia",
        "search_query": "Roman Colosseum ruins",
        "highlight_phrase": "THIRD PARALLEL",
    },
    {
        "text": "The United States has pulled THAAD batteries and Patriot systems out of South Korea to cover the Middle East. The Pacific gap is now real and measurable. Every analyst in Beijing can see it on a map. History does not repeat. But the structure of overextension does. Every time.",
        "footage_keyword": "world map military assets redeployment arrows Middle East Pacific",
        "footage_mood": "analytical",
        "source_type": "dalle",
        "search_query": "world map dark military redeployment arrows Middle East Pacific gap strategic",
        "highlight_phrase": "THE STRUCTURE OF OVEREXTENSION",
    },
    {
        "text": "Where does Jiang's full scorecard stand — Day 15 of the Iran war?",
        "footage_keyword": "prediction scorecard five items 2026 status update",
        "footage_mood": "analytical",
        "source_type": "motion_graphic",
        "search_query": "prediction scorecard five items 2026 status update",
        "highlight_phrase": None,
    },
    {
        "text": "Prediction 1 — Trump attacks Iran in early 2026: CONFIRMED. Operation Epic Fury launched February 28.",
        "footage_keyword": "Prediction 1 Trump attacks Iran CONFIRMED scorecard",
        "footage_mood": "dramatic",
        "source_type": "motion_graphic",
        "search_query": "Prediction 1 — Trump attacks Iran in early 2026",
        "highlight_phrase": "CONFIRMED",
    },
    {
        "text": "Prediction 2 — Airstrikes impressive but insufficient: CONFIRMED. Approximately 6,000 targets struck. Iran's military capacity degraded. The country has not capitulated. CFR and Chatham House both agree.",
        "footage_keyword": "Prediction 2 airstrikes insufficient CONFIRMED scorecard",
        "footage_mood": "dramatic",
        "source_type": "motion_graphic",
        "search_query": "Prediction 2 — Airstrikes impressive but insufficient",
        "highlight_phrase": "CONFIRMED",
    },
    {
        "text": "Prediction 3 — A costly war of attrition follows: CONFIRMED, ACTIVE. The US is burning 1.43 to 2 billion dollars per day. First week alone: over eleven billion. No Congressional authorization. No visible exit strategy.",
        "footage_keyword": "Prediction 3 war of attrition CONFIRMED ACTIVE scorecard",
        "footage_mood": "tense",
        "source_type": "motion_graphic",
        "search_query": "Prediction 3 — A costly war of attrition follows",
        "highlight_phrase": "CONFIRMED, ACTIVE",
    },
    {
        "text": "Prediction 4 — Russia and China exploit the distraction: ACTIVE. Russia is feeding Iran targeting data on US forces. Oil revenues funding the Ukraine war. China playing mediator while quietly noting the Pacific has fewer American assets in it.",
        "footage_keyword": "Prediction 4 Russia China exploit distraction ACTIVE scorecard",
        "footage_mood": "ominous",
        "source_type": "motion_graphic",
        "search_query": "Prediction 4 — Russia and China exploit the distraction",
        "highlight_phrase": "ACTIVE",
    },
    {
        "text": "Prediction 5 — The Iran war ends the US-led unipolar moment: ACTIVE, EARLY STAGE. Here is what active looks like right now. The UK says the strikes are inconsistent with the principles it thought it shared with America. Canada has called them inconsistent with international law. Poland is publicly worried the war is draining weapons from Ukraine. The G7 met and agreed only to 'look into' escorting ships through the Strait of Hormuz. Not to do it. To look into it.",
        "footage_keyword": "Prediction 5 unipolar moment ACTIVE early stage scorecard",
        "footage_mood": "ominous",
        "source_type": "motion_graphic",
        "search_query": "Prediction 5 — The Iran war ends the US-led unipolar moment",
        "highlight_phrase": "ACTIVE — EARLY STAGE",
    },
    {
        "text": "Foreign Affairs is running debates asking whether the unipolar moment has already ended. Brookings is publishing on whether this war accelerates American strategic decline. The Atlantic Council is asking twenty questions about the long-term consequences of the Iran war — and none of the answers are reassuring. This is not the end of the unipolar moment. But it may be the moment historians point to later and say: that is where it became irreversible.",
        "footage_keyword": "newspaper headlines magazine dark geopolitical crisis dramatic",
        "footage_mood": "ominous",
        "source_type": "stock",
        "search_query": "newspaper headlines dark dramatic geopolitical crisis magazine",
        "highlight_phrase": "THAT IS WHERE IT BECAME IRREVERSIBLE",
    },
    {
        "text": "Here is the objection I know some of you are loading right now. America has been declared in decline before. After Vietnam. After Iraq. After 2008. It came back every time. So why is this different? That is the strongest version of the counterargument. Hold it. Because the Suez parallel answers it directly — and the answer depends on one variable that has changed. Drop it in the comments.",
        "footage_keyword": "debate argument two sides confrontation dramatic dark",
        "footage_mood": "tense",
        "source_type": "stock",
        "search_query": "debate argument confrontation two sides dramatic dark",
        "highlight_phrase": "ONE VARIABLE THAT HAS CHANGED",
    },
    {
        "text": "Britain's unipolar moment did not end the day Suez failed. It ended slowly, and then suddenly. The people living through it largely did not see it in real time. Are we in that same slow-then-sudden moment right now — or is this just another scare cycle America weathers? Put your best argument in the comments. The strongest case against Prediction 5 gets pinned.",
        "footage_keyword": "hourglass close up sand timer dark dramatic countdown",
        "footage_mood": "dramatic",
        "source_type": "stock",
        "search_query": "hourglass close up sand timer dark dramatic",
        "highlight_phrase": "SLOWLY, AND THEN SUDDENLY",
    },
    {
        "text": "If Jiang's framework holds, Prediction 5 does not resolve this year. It resolves over the next decade — in trade routes, currency systems, and alliance structures being quietly renegotiated right now. Subscribe to follow it in real time. The next video covers the one actor who stands to gain the most from everything happening in Iran. And it is not the country you are thinking of.",
        "footage_keyword": "subscribe notification bell screen dark dramatic glow",
        "footage_mood": "dramatic",
        "source_type": "stock",
        "search_query": "subscribe notification bell screen dark dramatic glow",
        "highlight_phrase": None,
    },
]

script = " ".join(s["text"] for s in segments)

description = """The US is burning $2 billion/day on a war Congress never authorized. Its military admitted it can't keep the Strait of Hormuz open. And one analyst predicted this structural collapse months before the first bomb dropped.

Prof. Jiang Xueqin's Prediction 5: the Iran war will mark the end of the US-led unipolar moment. Three historical parallels — Suez 1956, Vietnam, Rome — and a full scorecard update on all five predictions.

━━━━━━━━━━━━━━━━━━━━━━━━
WATCH VIDEO #004 FIRST (Prediction 4 — Russia moving):
[link]
━━━━━━━━━━━━━━━━━━━━━━━━

SOURCES:
Iran war cost / overstretch:
• CSIS — $3.7B first 100 hours: https://www.csis.org/analysis/37-billion-estimated-cost-epic-furys-first-100-hours
• Al Jazeera — $2B/day: https://www.aljazeera.com/news/2026/3/9/is-the-iran-war-really-costing-the-us-2bn-per-day
• US military not ready to escort ships: https://www.aljazeera.com/news/2026/3/12/us-military-not-ready-to-escort-oil-ships-through-hormuz-official-says

Russia/China moves:
• Russia feeding Iran targeting intel — CNN: https://www.cnn.com/2026/03/06/politics/russia-aiding-iran-targeting
• China defense budget increase — AEI: https://www.aei.org/foreign-and-defense-policy/five-takeaways-on-china-and-the-iran-war/
• THAAD/Patriots redeployed from South Korea — SCMP: https://www.scmp.com/news/china/military/article/3346239/china-stands-gain-us-moving-military-assets-iran-war-cross-strait-adviser

Allies distancing:
• UK response — House of Commons: https://commonslibrary.parliament.uk/research-briefings/cbp-10521/
• Reactions to 2026 Iran war — Wikipedia: https://en.wikipedia.org/wiki/Reactions_to_the_2026_Iran_war
• G7 — only agreed to "look into" Hormuz escorts: multiple sources

Unipolar moment analysis:
• Foreign Affairs — Did the Unipolar Moment Ever End?: https://www.foreignaffairs.com/ask-the-experts/did-unipolar-moment-ever-end
• Brookings — After the strike: https://www.brookings.edu/articles/after-the-strike-the-danger-of-war-in-iran/
• Atlantic Council — Twenty questions: https://www.atlanticcouncil.org/dispatches/twenty-questions-and-expert-answers-about-the-iran-war/

Prof. Jiang Xueqin framework:
• Glenn Diesen Substack: https://glenndiesen.substack.com/p/jiang-xueqin-predictions-for-2026

━━━━━━━━━━━━━━━━━━━━━━━━
@PredictiveEchoes — tracking Jiang's predictions as they resolve.
"""

data = {
    "title": "Prof. Jiang's Most Dangerous Prediction Is Coming True Right Now",
    "description": description,
    "tags": [
        "jiang xueqin prediction 5", "unipolar moment end", "iran war 2026",
        "us empire decline", "suez 1956 parallel", "geopolitics 2026",
        "psychohistory game theory", "prediction scorecard", "us overstretch",
        "iran war unipolar moment", "us decline", "empire collapse history",
        "game theory geopolitics", "predictive history",
    ],
    "thumbnail_prompt": "Large white bold text 'THE UNIPOLAR MOMENT' on very dark background #080814, orange horizontal accent bar below it, orange sub-text 'IS IT ALREADY OVER?', Prof. Jiang Xueqin photo right side",
    "thumbnail_text": "THE UNIPOLAR MOMENT",
    "thumbnail_subtext": "IS IT ALREADY OVER?",
    "word_count": len(script.split()),
    "keywords": [
        "unipolar moment iran war", "suez 1956 america parallel",
        "jiang xueqin prediction five", "us overstretch iran",
        "thaad south korea redeployed", "g7 hormuz look into",
        "foreign affairs unipolar moment", "rome frontier overextension",
    ],
    "segments": segments,
    "script": script,
    "_meta": {
        "topic": "Prediction 5 — The Iran war ends the US-led unipolar moment",
        "generated_at": datetime.now().isoformat(),
        "model": "manual",
        "note": "Script written manually from deep web research pass (2026-03-15). Two-step refinement: humanizer + copywriting agents applied.",
        "research_date": "2026-03-15",
        "estimated_cost": "$3.25 (voice ~$2.45 + DALL-E ~$0.64 + vision ~$0.20)",
    },
}

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
slug = "prediction_five_unipolar_moment_iran_war"
filename = f"{timestamp}_{slug}.json"
output_path = DRAFTS_DIR / filename

output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

script_path = DRAFTS_DIR / f"{timestamp}_{slug}_script.txt"
script_path.write_text(
    f"TITLE: {data['title']}\n\nWORD COUNT: {data['word_count']}\n\n{'='*60}\nSCRIPT\n{'='*60}\n\n{script}",
    encoding="utf-8",
)

print(f"Draft JSON saved: {output_path}")
print(f"Script TXT saved: {script_path}")
print(f"Segments: {len(segments)}")
print(f"Word count: {data['word_count']}")
