"""
One-time script to create the Video #003 draft JSON from the pre-written final script.
Run: python create_video003_draft.py
"""
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
DRAFTS_DIR = ROOT / "outputs" / "drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

segments = [
    {
        "text": "Russia didn't invade the Baltics. China didn't move on Taiwan. And most analysts declared Prediction Four a miss. They were looking at the wrong thing.",
        "footage_keyword": "chess board dark dramatic two kings facing",
        "footage_mood": "tense",
        "source_type": "stock",
        "search_query": "chess kings dark board dramatic close up",
        "highlight_phrase": "THEY WERE LOOKING AT THE WRONG THING",
    },
    {
        "text": "In the last video, I walked through five predictions Professor Jiang Xueqin made for 2026. Four of them have either confirmed or are actively unfolding. If you haven't seen that video, the link is in the description — watch it first, then come back. Because what I'm about to show you only makes sense if you understand how Jiang thinks.",
        "footage_keyword": "Jiang Xueqin official portrait",
        "footage_mood": "analytical",
        "source_type": "dalle",
        "search_query": "Jiang Xueqin official portrait",
        "highlight_phrase": None,
    },
    {
        "text": "Here is what most people get wrong about Prediction Four. They heard \"Russia and China exploit US distraction\" and went looking for tanks crossing borders. That is not how great powers operate when the math is working in their favor.",
        "footage_keyword": "military tanks convoy dark dramatic wide shot",
        "footage_mood": "dramatic",
        "source_type": "stock",
        "search_query": "military tanks convoy dramatic dark",
        "highlight_phrase": "NOT HOW GREAT POWERS OPERATE",
    },
    {
        "text": "Jiang's framework is not about predicting invasions. It's about predicting what rational actors are forced to do when the incentive structures shift. Game theory doesn't ask what a player wants — it asks what a player's dominant strategy is given the payoffs in front of them.",
        "footage_keyword": "empire payoff matrix game theory abstract visualization",
        "footage_mood": "analytical",
        "source_type": "dalle",
        "search_query": "empire payoff matrix game theory abstract visualization",
        "highlight_phrase": "WHAT RATIONAL ACTORS ARE FORCED TO DO",
    },
    {
        "text": "Right now, Russia's dominant strategy is not to launch a new war. It's to bleed America quietly while America's attention is somewhere else. An invasion would invite unified Western response, international sanctions, and a NATO tripwire. What Russia is doing instead is far more dangerous — because it works, and Washington isn't treating it like a threat. That is not a failure of Prediction Four. That is Prediction Four.",
        "footage_keyword": "chess player dark silhouette strategic move close up",
        "footage_mood": "tense",
        "source_type": "stock",
        "search_query": "chess player dark shadow strategy dramatic",
        "highlight_phrase": "THAT IS PREDICTION FOUR",
    },
    {
        "text": "On March 6, 2026, multiple US officials confirmed to the Washington Post, CNN, and NBC News that Russia is providing Iran with satellite imagery — real-time targeting intelligence on the locations of US warships and aircraft operating in the Middle East.",
        "footage_keyword": "satellite imagery dark intelligence monitor screens glow",
        "footage_mood": "ominous",
        "source_type": "stock",
        "search_query": "satellite imagery dark monitor screen intelligence surveillance",
        "highlight_phrase": "REAL-TIME TARGETING INTELLIGENCE",
    },
    {
        "text": "Russia is feeding coordinates of American forces to a country actively firing missiles at American bases. The Pentagon's response: Secretary Hegseth said he was \"not concerned.\" Read that again. Not concerned.",
        "footage_keyword": "missile launch dramatic night sky military dark",
        "footage_mood": "dramatic",
        "source_type": "stock",
        "search_query": "missile launch night sky dramatic dark military",
        "highlight_phrase": "NOT CONCERNED",
    },
    {
        "text": "Your adversary is giving your enemy a targeting map, and the response is that it doesn't rise to the level of concern. That tells you everything about how badly America has miscalibrated what a conflict with Russia actually looks like.",
        "footage_keyword": "war room military command screens dark dramatic",
        "footage_mood": "tense",
        "source_type": "stock",
        "search_query": "military command center dark screens war room",
        "highlight_phrase": "HOW BADLY AMERICA HAS MISCALIBRATED",
    },
    {
        "text": "Ukraine's President Zelensky stated publicly that more Patriot interceptor missiles were consumed in three days of the Iran campaign than Ukraine has received since 2022. The United States produces roughly 600 PAC-3 interceptors per year. Iran consumed the equivalent of that entire annual production in seventy-two hours.",
        "footage_keyword": "Patriot missile battery launch defense system night",
        "footage_mood": "dramatic",
        "source_type": "stock",
        "search_query": "Patriot missile battery launch night sky defense",
        "highlight_phrase": "600 INTERCEPTORS. SEVENTY-TWO HOURS.",
    },
    {
        "text": "Russia knows this. And Russia is now striking Ukrainian energy infrastructure in the gaps left by a depleted air defense. Ukrainian cities are going dark. Not because Russia got stronger — because America's missiles are pointed at Iran.",
        "footage_keyword": "city power blackout darkness aerial night urban",
        "footage_mood": "ominous",
        "source_type": "stock",
        "search_query": "city power blackout darkness aerial night urban",
        "highlight_phrase": "UKRAINIAN CITIES ARE GOING DARK",
    },
    {
        "text": "Meanwhile, the Ukraine ceasefire talks in Geneva — prisoner exchanges on March 5 and 6, five hundred soldiers total — remain completely stalled on territorial terms. Putin is simultaneously demanding the US halt Iran operations while refusing any ground-level ceasefire in Ukraine. He is using the Iran war as diplomatic leverage to extract concessions on Ukraine. That is not opportunism. That is a coordinated strategy running on two tracks at once while Washington is focused on one.",
        "footage_keyword": "negotiation table two sides stalled confrontation dramatic",
        "footage_mood": "tense",
        "source_type": "stock",
        "search_query": "negotiation table stalled two sides tense dramatic",
        "highlight_phrase": "A COORDINATED STRATEGY",
    },
    {
        "text": "First. When Athens launched the Sicilian Expedition in 415 BC — its most ambitious military operation at the height of its power — Sparta did not immediately counterattack. Sparta waited. It let Athens exhaust itself across the water, then reopened the war on the Greek mainland while Athenian forces were pinned down in Sicily. The expedition destroyed not just an army but Athens's entire strategic reserve. Jiang draws the direct parallel: empires do not fall to a single decisive blow. They fall because rivals are patient enough to let overreach do the work.",
        "footage_keyword": "ancient Greek ruins columns dramatic sky empire",
        "footage_mood": "dramatic",
        "source_type": "dalle",
        "search_query": "ancient Greek empire map Sicily Athens Sparta parchment",
        "highlight_phrase": "RIVALS ARE PATIENT ENOUGH",
    },
    {
        "text": "Second. In 1956, while Britain was consumed by the Suez Crisis — militarily successful, diplomatically catastrophic — the Soviet Union crushed the Hungarian Revolution. It did so without meaningful Western response, because the West's political and military attention was locked onto Egypt. The window was not created by Soviet strength. It was created by British distraction. Russia providing targeting intelligence to Iran while simultaneously striking Ukrainian energy infrastructure is the 2026 version of that calculation. The script hasn't changed. Only the names.",
        "footage_keyword": "Suez Crisis British Egypt 1956 military intervention",
        "footage_mood": "dramatic",
        "source_type": "archive",
        "search_query": "Suez Crisis British forces Egypt 1956",
        "highlight_phrase": "THE SCRIPT HASN'T CHANGED",
    },
    {
        "text": "Third. Between 1965 and 1973, while the United States poured resources into Vietnam, the Soviet Union achieved strategic nuclear parity with America — going from clear inferiority to rough equivalence in deployed warheads and delivery systems. The Soviets didn't win Vietnam. They didn't need to. They used the decade of American distraction to close the gap that mattered.",
        "footage_keyword": "Cold War Soviet nuclear missile ICBM launch 1960s",
        "footage_mood": "ominous",
        "source_type": "archive",
        "search_query": "Soviet nuclear missile Cold War 1960s ICBM",
        "highlight_phrase": "THEY DIDN'T NEED TO WIN",
    },
    {
        "text": "Now look at North Korea. Its new destroyer — the Choe Hyon, a 5,000-ton warship with nuclear-capable cruise missiles — was personally inspected by Kim Jong Un on March 3 and 4. The final cruise missile test was conducted. Kim called for two destroyers per year. This is a country accelerating its military development during an American distraction. The historical template is exact. The question is whether Washington is reading it.",
        "footage_keyword": "North Korea destroyer warship naval military launch",
        "footage_mood": "ominous",
        "source_type": "wikimedia",
        "search_query": "North Korea destroyer warship Choe Hyon naval military",
        "highlight_phrase": "ACCELERATING DURING AN AMERICAN DISTRACTION",
    },
    {
        "text": "Now the full scorecard. Five predictions Jiang made for 2026.",
        "footage_keyword": "five prediction scorecard 2026 status tracker graphic",
        "footage_mood": "analytical",
        "source_type": "motion_graphic",
        "search_query": "five prediction scorecard 2026 status tracker graphic",
        "highlight_phrase": None,
    },
    {
        "text": "Prediction one — Trump attacks Iran in early 2026. Confirmed. US-Israel joint strike, February 28. Khamenei killed. Multi-city strikes across Tehran, Isfahan, Qom, Tabriz.",
        "footage_keyword": "prediction one scorecard CONFIRMED Trump attacks Iran early 2026",
        "footage_mood": "dramatic",
        "source_type": "motion_graphic",
        "search_query": "Prediction one — Trump attacks Iran in early 2026",
        "highlight_phrase": "CONFIRMED",
    },
    {
        "text": "Prediction two — Airstrikes are impressive but strategically insufficient. Confirmed. CFR analysts, Max Boot, Chatham House — all on record. Airstrikes cannot produce regime change without ground troops. Iran is still fighting.",
        "footage_keyword": "prediction two scorecard CONFIRMED airstrikes strategically insufficient",
        "footage_mood": "dramatic",
        "source_type": "motion_graphic",
        "search_query": "Prediction two — Airstrikes are impressive but strategically insufficient",
        "highlight_phrase": "CONFIRMED",
    },
    {
        "text": "Prediction three — The conflict becomes a costly war of attrition. Active. Iran has retaliated against 27 US regional bases. The Strait of Hormuz closure threat alone is sending oil markets into shock.",
        "footage_keyword": "prediction three scorecard ACTIVE war of attrition costly",
        "footage_mood": "tense",
        "source_type": "motion_graphic",
        "search_query": "Prediction three — The conflict becomes a costly war of attrition",
        "highlight_phrase": "ACTIVE",
    },
    {
        "text": "Prediction four — Russia and China exploit US distraction. Active — and accelerating. Russia is feeding targeting intelligence on US forces to Iran. Russia is striking Ukraine's energy grid through Patriot missile gaps. Putin is using the Iran war as diplomatic leverage to stall Ukraine talks. North Korea just tested a nuclear-capable cruise missile from its new destroyer. China condemned the Iran strikes at the UN Security Council, requested an emergency session, and analysts are actively debating whether US distraction opens a Taiwan window. BRICS failed to respond collectively — and that failure itself tells you something. The bloc that was supposed to be the counterweight to American power couldn't agree on a statement when one of its members was bombed. What does that mean for the balance of power going forward?",
        "footage_keyword": "prediction four scorecard ACTIVE Russia China exploit US distraction",
        "footage_mood": "ominous",
        "source_type": "motion_graphic",
        "search_query": "Prediction four — Russia and China exploit US distraction",
        "highlight_phrase": "ACTIVE — AND ACCELERATING",
    },
    {
        "text": "Prediction five — The Iran war marks the end of the US-led unipolar moment. Still pending confirmation. But look at the trajectory. America's most advanced missile defense system is being depleted by a regional conflict. Its chief rival is feeding targeting coordinates of its forces to an enemy. Its proxy war in Ukraine is being exploited as leverage. And the bloc that was meant to challenge US hegemony is fracturing under pressure. Jiang said this was the beginning of a new balance of power favoring the East. The scoreboard is not there yet. But every single structural indicator is pointing in that direction.",
        "footage_keyword": "prediction five scorecard PENDING end US unipolar moment",
        "footage_mood": "ominous",
        "source_type": "motion_graphic",
        "search_query": "Prediction five — The Iran war marks the end of the US-led unipolar moment",
        "highlight_phrase": "EVERY INDICATOR POINTING THAT DIRECTION",
    },
    {
        "text": "So here is the one question I want you to answer. Russia's dominant strategy right now is to bleed America slowly — not through direct confrontation, but through intel support to Iran, energy strikes on Ukraine, and diplomatic stalling. Does that strategy eventually force a direct US-Russia confrontation? Or does America recognize the trap and find a way out before the overstretch becomes irreversible? Tell me in the comments. I read every one.",
        "footage_keyword": "globe spinning dark cinematic geopolitical dramatic",
        "footage_mood": "dramatic",
        "source_type": "stock",
        "search_query": "globe spinning dark cinematic dramatic geopolitical",
        "highlight_phrase": None,
    },
    {
        "text": "If you want to follow this scorecard as it updates — subscribe. The next video tracks Prediction Five: whether the Iran war actually ends the unipolar moment, or whether America finds a way to reset the board. That one has a hard deadline. And it is approaching faster than anyone in Washington is admitting. Jiang's original 2026 predictions and all sources used in this video are linked in the description below.",
        "footage_keyword": "subscribe notification bell glowing screen dark background",
        "footage_mood": "dramatic",
        "source_type": "stock",
        "search_query": "subscribe notification bell screen dark dramatic glow",
        "highlight_phrase": None,
    },
]

script = " ".join(s["text"] for s in segments)

description = """Russia didn't invade anywhere. That's why most analysts missed it.

Professor Jiang Xueqin predicted Russia and China would exploit US distraction during the Iran war. This video shows exactly how that's unfolding — through satellite targeting intelligence, Patriot missile depletion, Ukraine energy strikes, and North Korea's new destroyer.

Full scorecard update: Predictions 1-5, where they stand now.

━━━━━━━━━━━━━━━━━━━━━━━━
WATCH VIDEO #002 FIRST:
https://www.youtube.com/watch?v=YJBmr6LjuWk
━━━━━━━━━━━━━━━━━━━━━━━━

SOURCES:
Russia targeting intel to Iran:
• Washington Post: https://www.washingtonpost.com/national-security/2026/03/06/russia-iran-intelligence-us-targets/
• CNN: https://www.cnn.com/2026/03/06/politics/russia-aiding-iran-targeting
• NBC News: https://www.nbcnews.com/politics/national-security/russia-providing-intelligence-iran-location-us-forces-sources-say-rcna262115
• PBS NewsHour: https://www.pbs.org/newshour/world/russia-gave-iran-information-that-can-help-tehran-hit-u-s-military-targets-ap-sources-say

Patriot missile shortage / Ukraine:
• Al Jazeera: https://www.aljazeera.com/news/2026/3/6/amid-iran-war-will-russia-exploit-ukraines-shortage-of-patriot-missiles
• Kyiv Post: https://www.kyivpost.com/post/47437
• ISW March 6: https://www.criticalthreats.org/analysis/russian-offensive-campaign-assessment-march-6-2026

North Korea destroyer:
• USNI News: https://news.usni.org/2026/03/06/north-korean-destroyer-tests-strategic-cruise-missile
• The Defense Post: https://thedefensepost.com/2026/03/05/north-korea-missile-tests/

China response:
• PRC Foreign Ministry: https://www.fmprc.gov.cn/mfa_eng/xw/fyrbt/202603/t20260303_11867987.html
• Chatham House: https://www.chathamhouse.org/2026/02/china-playing-long-game-over-iran
• Asia Times: https://asiatimes.com/2026/03/iran-war-make-a-china-attack-on-taiwan-more-likely/

BRICS divided:
• Al Jazeera: https://www.aljazeera.com/news/2026/3/6/is-brics-bloc-divided-over-us-israel-attacks-on-iran
• Middle East Eye: https://www.middleeasteye.net/news/brics-missing-in-action-israel-war-permanent-member-iran-spirals

Prof. Jiang Xueqin framework:
• Glenn Diesen Substack: https://glenndiesen.substack.com/p/jiang-xueqin-predictions-for-2026
• Wikipedia: https://en.wikipedia.org/wiki/Jiang_Xueqin
• Boreal Times: https://borealtimes.org/the-chain-reaction-toward-world-war-iii-has-begun/

━━━━━━━━━━━━━━━━━━━━━━━━
@PredictiveEchoes — tracking Jiang's predictions as they resolve.
"""

data = {
    "title": "Russia Is Already Winning — And America Doesn't See It Yet",
    "description": description,
    "tags": [
        "russia iran war", "jiang xueqin predictions", "predictive history",
        "russia ukraine patriot missiles", "north korea destroyer", "china taiwan",
        "us empire decline", "geopolitics 2026", "game theory geopolitics",
        "iran war 2026", "prediction scorecard", "brics divided",
        "russia exploiting distraction", "unipolar moment end",
    ],
    "thumbnail_prompt": "Bold text RUSSIA IS WINNING on dark background, world map with red lines connecting Middle East and Ukraine, ominous cinematic",
    "thumbnail_text": "RUSSIA IS WINNING",
    "word_count": len(script.split()),
    "keywords": [
        "russia iran targeting intelligence", "patriot missile shortage ukraine",
        "north korea choe hyon destroyer", "jiang xueqin prediction four",
        "game theory dominant strategy", "empire decline overstretch",
        "brics divided iran war", "china taiwan window us distraction",
    ],
    "segments": segments,
    "script": script,
    "_meta": {
        "topic": "Russia and China exploiting US distraction during Iran war — Jiang Prediction 4 update",
        "generated_at": datetime.now().isoformat(),
        "model": "manual",
        "note": "Script written manually, segmented and formatted for pipeline",
    },
}

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
slug = "russia_is_already_winning_prediction_four_update"
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
