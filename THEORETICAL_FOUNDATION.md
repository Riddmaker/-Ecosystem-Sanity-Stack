# Theoretical Foundation — Ecosystem Sanity Stack

## v4 Framework: 2-Axis Reading

The dashboard asks two independent questions:

1. **Is this emotion manufactured or authentic?** → Ragebait Index (0–10, higher = worse)
2. **How heavy is this content to process?** → Emotional Weight (0–10, neutral)

The combination of both axes tells the real story:

| Article | Ragebait | Weight | Read as |
|---|---|---|---|
| Iran-Kriegs-Livefeed | Low (1–2) | High (9–10) | Authentic heavy news — legitimate, but take breaks |
| Baby-Reisen Streit | High (8–10) | Low (1–3) | Pure clickbait — no substance, manufactured conflict |
| Wetter/Lifestyle | Low (1–2) | Low (1–2) | Clean informational content |
| Iran-Malediven-Ferien | Medium (6–7) | Medium (4–6) | Angle exploitation — war as clickbait backdrop |
| War content + conflict staging | High (8–10) | High (8–10) | Worst pattern: exploitation of real suffering |

**The dashboard message is not:** "avoid emotional content"
**The dashboard message is:** "be aware when emotions are being manufactured"

---

## Ragebait Index — Theoretical Foundation

### Curiosity Gap
> *"The headline withholds information that honest reporting would include."*

**Blom & Hansen (2015)**
Journalism Practice — DOI: [10.1080/17512786.2014.976939](https://doi.org/10.1080/17512786.2014.976939)

«Click bait: Forward-reference as lure in online news headlines.»
Coined the concept of "Forward-reference": headlines that reference something in the text
but deliberately withhold it to force clicks. Empirical analysis of Danish news sites.

Sub-score: **curiosity_gap** — Does the headline promise something it doesn't deliver?

---

### Emotional Inflation (Linguistic Manipulation)
> *"Emotional adjectives are used without factual backing."*

**Potthast et al. (2016)**
ECIR — DOI: [10.1007/978-3-319-30671-1_72](https://doi.org/10.1007/978-3-319-30671-1_72)

«Clickbait Detection» — Developed ML classifiers using linguistic features.
Key finding: clickbait correlates strongly with high ratio of emotional adjectives
to verifiable facts. «skandalös», «empörend», «unglaublich» without evidence.

Sub-score: **emotional_inflation** — Are emotional claims backed by concrete facts?

---

### Conflict Staging (Engagement Baiting Patterns)
> *"Groups are artificially pitted against each other to generate engagement."*

**Rony, Hassan & Yousuf (2017)**
ACM WebSci — DOI: [10.1145/3091478.3091487](https://doi.org/10.1145/3091478.3091487)

«Diving Deep into Clickbaits» — Taxonomized clickbait patterns including
"Engagement Farming through Controversy Manufacturing": articles whose sole purpose
is to stage conflict between groups («die Community ist gespalten») to harvest comments.

Sub-score: **conflict_staging** — Is conflict manufactured for engagement?

---

## Wellbeing Foundation (why manufactured emotion is harmful)

These three studies explain **why** the Ragebait Index matters — what manufactured
emotional content does to the reader over time. They are the theoretical backdrop,
not scored dimensions.

### The Consumption Spiral

**McLaughlin, Gotlieb & Mills (2022)**
Health Communication — DOI: [10.1080/10410236.2022.2106086](https://doi.org/10.1080/10410236.2022.2106086)

Validated clinical scale for Problematic News Consumption. Direct correlation with
anxiety, depression, sleep disturbance. Regular consumers of high-urgency content
must spend increasing energy to avoid consuming even more.

*Why it matters:* High-ragebait content is specifically designed to trigger this spiral.

---

### The Distorted World

**McNaughton-Cassill & Smith (2002)**
Stress and Health — DOI: [10.1002/smi.916](https://doi.org/10.1002/smi.916)

"Optimism Gap": news consumers systematically overestimate national threats
relative to their direct lived experience. Correlates with helplessness and
irrational beliefs about the state of the world.

*Why it matters:* Emotional inflation and conflict staging directly feed this distortion.

---

### Outrage Depletion

**Crockett, M.J. (2017)**
Nature Human Behaviour — DOI: [10.1038/s41562-017-0213-3](https://doi.org/10.1038/s41562-017-0213-3)

"Moral Outrage in the Digital Age." Digital media reduce the cost of outrage
expression (liking, sharing) to near zero. Result: habituation (outrage stimulus
loses effect) + moral licensing (online outrage replaces real action).
Manufactured outrage crowds out legitimate moral response.

*Why it matters:* High-ragebait content systematically depletes genuine moral capacity.

---

## Score Architecture

### Ragebait Index (0–10, higher = worse)
```
composite = holistic assessment
sub-scores: curiosity_gap · conflict_staging · emotional_inflation
```

### Emotional Weight (0–10, neutral)
```
composite = holistic assessment
sub-scores: topic_gravity · emotional_exposure · reader_burden
```

Modell: `mistral-large-latest` · Temperature: `0.0` · Seed: `42`
Prompt Version: `v4`

---

## Designentscheide v4

- **Ragebait statt Sanity Score** — misst Fabrikation, nicht Effekt. Erlaubt Unterscheidung
  authentischer (Krieg) von fabrizierter (Baby-Streit) Emotion.
- **Emotional Weight als neutraler Deskriptor** — kein Qualitätsurteil. Hoher Weight bei
  tiefem Ragebait = legitime schwere Nachrichten, nicht schlechte Nachrichten.
- **Civic Utility entfernt** — war konzeptuell sauber aber UI-seitig verwirrend.
  Die 2-Achsen-Lesart ist klarer und direkter.
- **Brady et al. (2017) vollständig entfernt** — misst Virality, nicht Wellbeing.
- **Ursprüngliche 3 Wellbeing-Studien behalten** — erklären warum Ragebait schadet,
  aber sind keine gescorten Dimensionen mehr.
