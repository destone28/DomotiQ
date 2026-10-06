# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
"""What the house knows about its characters: the answers to its questions, and questions about them.

- **Answers become facts.** When a character answers a question of chatty
  mode that tells something lasting about it ("qual è il tuo piatto
  preferito?" - "la pizza"), the answer joins its facts, written as it would
  be said after the name ("adora mangiare la pizza") in the language of the
  conversation. The web app shows the facts and the stories use them. Each
  question keeps one line: a new answer takes the place of the old one, in
  either language, and when the list is full an older answer makes room,
  never a line somebody typed.
- **Both languages.** A line made from an answer is read back through its
  template, so the house can say it in the other language too.
- **Questions about a character.** "Cosa mangia Rossellina?", "cosa posso
  cucinare a Rossellina?", "what does Rossellina like to eat?": keywords of
  both languages tell the topic of the question (food, music, where somebody
  comes from...) and of every fact. The language model tells the topic of
  what the keywords miss ("Marco cura i malati?"), and of the facts typed in
  the web app that no keyword describes; its output is one topic, forced by a
  grammar. The answer is the fact itself after the name, so it is never made
  up and agrees with any name; when no fact has that topic the house says
  that it does not know.

Measured with Qwen2.5-0.5B on 164 questions about six characters: the
keywords answer 99% of the questions phrased the usual ways, the model finds
about a third of the facts asked with no keyword at all, and one answer in
164 is a wrong fact. Asking the model to pick the fact by its number
(18-48%) or to write the answer (43-62%, with facts it made up) did much
worse.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any, Iterable

from .intents import normalize

# ------------------------------------------------------------------ topics
# What a question or a fact is about, by keywords of both languages on normalized text (no accents,
# apostrophes as spaces). For a question the first topic of this list that matches counts: "cosa mangia
# la sera" is about food, not about the evening.
TOPICS: list[tuple[str, str]] = [
    ("food", r"\bmangi\w*|\bgrigliat\w*|\bbarbecue\b|\bbbq\b|\bgrill\w*|\bmange\w*|\bcib[oi]\b|\bpiatto\b|\bpranz\w*|\bcen[ae]\b|\bcenare\b|\bcolazion\w*|"
             r"\bmerend\w*|\bcucinar\w*|\bcucinat\w*|\bcucino\b|\bcucini\b|\bricett\w*|\bgolos\w*|\bpizz\w*|"
             r"\bristorant\w*|\btrattori\w*|\brestaurants?\b|"
             r"\bpasta\b|\bspaghett\w*|\blasagn\w*|\brisott\w*|\bgelat\w*|\bcroccantin\w*|\bcrocchett\w*|"
             r"\beat\w*|\bate\b|\bfoods?\b|\bdish\b|\bmeals?\b|\blunch\w*|\bdinners?\b|\bbreakfast\w*|\bcook\w*|"
             r"\brecipes?\b|\bsnacks?\b|\bhungry\b|\bkibble\b"),
    ("drink", r"\bbev[eo]\w*|\bbere\b|\bbevand\w*|\bcaffe\b|\bvino\b|\bbirr\w*|\bsucc(o|hi)\b|\bdrink\w*|\bcoffee\b|"
              r"\btea\b|\bwine\b|\bbeers?\b|\bjuice\b"),
    ("colour", r"\bcolor\w*|\bcolour\w*|\bross[oa]\b|\bverde\b|\bblu\b|\bgiall[oa]\b|\barancion\w*|\bviola\b|"
               r"\brosa\b|\bbianc[oa]\b|\bazzurr[oa]\b|\bceleste\b|\bner[oa]\b|\bgrigi[oa]\b|\bmarrone\b|\bred\b|"
               r"\bgreen\b|\bblue\b|\byellow\b|\borange\b|\bpurple\b|\bviolet\b|\bpink\b|\bwhite\b|\bblack\b|"
               r"\bgr[ae]y\b|\bbrown\b"),
    ("music", r"\bmusic\w*|\bball[aio]\w*|\bdanc\w*|\bcanzon\w*|\bcantant\w*|\bcant[ao]\b|\bcantare\b|\bascolt\w*|\bradio\b|\bconcert\w*|"
              r"\bband\b|\bsuon\w*|\bstrument\w*|\bpianoforte\b|\bchitarr\w*|\bviolin\w*|\bbatteria\b|\bjazz\b|"
              r"\brock\b|\bpop\b|\brap\b|\bopera\b|\bblues\b|\bsongs?\b|\bsing(s|ing|er|ers)?\b|\blisten\w*|"
              r"\binstruments?\b|\bguitar\w*|\bdrums?\b|\bpiano\b"),
    ("sport", r"\bsport\w*|\bcalcio\b|\btennis\b|\bnuot\w*|\bpalestra\b|\bsquadr\w*|\btif[ao]\w*|\bpartit[ae]\b|"
              r"\bbici\w*|\bcors[ae]\b|\bcorrere\b|\bpallavolo\b|\bbasket\b|\bsci\b|\bsciare\b|\bgioc\w* a\b|"
              r"\bjuventus\b|\binter\b|\bmilan\b|\bfootball\b|\bsoccer\b|\bteams?\b|\bsupports?\b|\bmatch(es)?\b|"
              r"\bgym\b|\bswim\w*|\bcycl\w*|\bski(s|ing)?\b|\bvolleyball\b|\bbasketball\b|\bgolf\b|\brugby\b"),
    ("job", r"\blavor\w*|\bmestier\w*|\bprofession\w*|\bimpieg\w*|\binsegn\w*|\bjobs?\b|\bwork(s|ing)?\b|"
            r"\bcareer\b|\bfor a living\b|\boccupation\b|\bteach\w*|\bufficio\b|\bospedal\w*|\bmalati\b|"
            r"\bpazienti\b|\bclienti\b|\bcolleghi\b|\bnegozio\b|\bfabbrica\b|\bazienda\b|\bstipendio\b|"
            r"\bin pensione\b|\boffice\b|\bhospital\b|\bpatients\b|\bcustomers\b|\bcolleagues\b|\bretired\b"),
    ("fear", r"\bpaur\w*|\bspavent\w*|\bterror\w*|\btem[ei]\b|\bfobi\w*|\bafraid\b|\bscared?\b|\bfears?\b|"
             r"\bfrighten\w*|\bphobi\w*"),
    ("hobby", r"\bhobb\w*|\btempo libero\b|\bpassion\w*|\bcollezion\w*|\bpassatemp\w*|\bfree time\b|"
              r"\bspare time\b|\bcollect\w*|\bpastimes?\b"),
    ("travel", r"\bmare\b|\bmontagn\w*|\bmonti\b|\bspiagg\w*|\bvacanz\w*|\bviagg\w*|\bferie\b|\blago\b|"
               r"\bsea\b|\bseaside\b|\bbeach\w*|\bmountains?\b|\bholidays?\b|\bvacations?\b|\btrips?\b|"
               r"\btravel\w*|\blake\b"),
    # where somebody likes to sit: only with a word of liking or habit, otherwise "Marco è sul divano?" and
    # "where is Marco sitting?" (where it is now) would be questions about it
    ("seat", r"\b(piac\w*|preferisc\w*|preferit\w*|ama|adora\w*|sempre|di solito|likes?|loves?|prefers?|"
             r"favou?rite|always|usually)\b.*\b(divan[oi]|poltron\w*|sedi[ae]|siede|sedersi|sofas?|couch|"
             r"armchairs?|sit|seats?)\b|"
             r"\b(divan[oi]|poltron\w*|sedi[ae]|siede|sedersi|sofas?|couch|armchairs?|sits?|seats?)\b.*"
             r"\b(piac\w*|preferisc\w*|preferit\w*|sempre|di solito|likes?|loves?|prefers?|favou?rite|always|"
             r"usually)\b"),
    ("origin", r"\b(vien[ei]|vengono) (da|dal|dallo|dalla|dall|dai|dagli|dalle)\b|\bdi dove\b|\bda dove\b|"
               r"\bnat[oaie]\b|\bnascit\w*|\bcitta\b|\bpaese\b|"
               r"\bnazion\w*|\borigin\w*|\babit(a|ano|are)\b|\b(dove vive|vive a|vive in)\b|\bborn\b|\bhometown\b|"
               r"\bcity\b|\bcountry\b|\bwhere\b.*\b(from|lives?)\b|\b(is|are|comes?|came) from\b|\blives in\b|"
               # where somebody comes from, said with the name of its people: "è torinese?", "is he British?";
               # only after "è"/"is" ("adora la cucina italiana" is about food)
               r"\b(e|sono|era|is|are|am|was|were)\s+(\w+\s+)?(un |una |a |an )?("
               r"(torines|milanes|genoves|bolognes|piemontes|pugli?es|calabres|ingles|frances|olandes|"
               r"portoghes|giappones|cines|londines|irlandes|scozzes|canades)[ei]|"
               r"(roman|napoletan|sicilian|toscan|venezian|fiorentin|lombard|italian|american|australian|"
               r"tedesc|spagnol|svizzer|brasilian|argentin|messican)[oaie]|"
               r"english|british|italian|french|german|spanish|american|irish|scottish|welsh|swiss|chinese|"
               r"japanese|dutch|londoner)\b"),
    ("animals", r"\banimal\w*|\bcan[ei]\b|\bcagnolin\w*|\bgatt[oi]\b|\bgattin\w*|\bpets?\b|\bdogs?\b|\bcats?\b|"
                r"\bpupp(y|ies)\b|\bkittens?\b"),
    ("family", r"\bfamigl\w*|\bfratell\w*|\bsorell\w*|\bfigli\w*|\bmamma\b|\bpapa\b|\bmadre\b|\bpadre\b|"
               r"\bmarit\w*|\bmoglie\b|\bnonn[oi]\b|\bzi[oi]\b|\bcugin\w*|\bsposat\w*|\bfidanzat\w*|\bfamil\w*|"
               r"\bbrothers?\b|\bsisters?\b|\bsons?\b|\bdaughters?\b|\bmother\b|\bfather\b|\bmum\b|\bmom\b|"
               r"\bdad\b|\bhusband\b|\bwife\b|\bmarried\b|\bchildren\b|\bcousins?\b|"
               r"\bgrand(mas?|pas?|mothers?|fathers?|parents?|sons?|daughters?|children|child|kids?)\b|"
               r"\bgirlfriend\b|\bboyfriend\b"),
    ("age", r"\bquanti anni\b|\beta\b|\bhow old\b|\bage\b"),
    # this house and its garden: only with a word of liking ("a Giulia piace il giardino?"), otherwise
    # "Giulia è in giardino?" would be a question about it
    ("home", r"\b(piac\w*|ama|adora\w*|likes?|loves?|fond)\b.*\b(casa|giardino|house|garden|home)\b|"
             r"\b(casa|giardino|house|garden|home)\b.*\b(piac\w*|likes?|loves?)\b"),
    ("sleep", r"\bmattin\w*|\bsera\b|\bnotte\b|\bnottambul\w*|\bsvegli\w*|\bsi alza\b|\balzarsi\b|\bdorm\w*|"
              r"\bsonno\b|\b(va|vanno|vai|andare) a letto\b|\bmornings?\b|\bevenings?\b|\bnights?\b|\bwakes?\b|"
              r"\bwaking\b|\bgets? up\b|\bsleep\w*|\bbedtime\b|\bgo(es)? to bed\b|\bearly riser\b|\bnight owl\b"),
]
TOPIC_IDS = [t for t, _ in TOPICS]
_TOPIC_RE = [(t, re.compile(p)) for t, p in TOPICS]
# words of liking: "cosa piace a Giulia?" is about the character even without a topic
LIKING = re.compile(r"\bpiac\w*|\bama\b|\bamano\b|\badora\w*|\bodi[ao]\b|\bpreferit\w*|\bpreferisc\w*|"
                    r"\b(va|vanno) (matt|pazz)\w* per\b|\bimpazzisc\w* per\b|\b(ha|hanno) un debole per\b|"
                    r"\b(is|are) (crazy|mad) about\b|\b(has|have) a soft spot for\b|"
                    r"\bpreferenz\w*|\bgust[oi]\b|\bsi trova bene\b|\bfavou?rites?\b|\bprefers?\b|\blikes?\b|"
                    r"\bloves?\b|\bhates?\b|\benjoys?\b|\bfond\b|\bkeen\b")
# a sentence that starts like a command is not a question about somebody ("metti la musica preferita di Anna")
COMMAND = re.compile(r"^(per favore |please )?(accendi|spegni|metti|fai|facciamo|apri|chiudi|alza|abbassa|porta|"
                     r"parla|parliamo|aggiungi|registra|turn|switch|put|play|make|set|start|stop|open|close|"
                     r"speak|add|register|let s|lets)\b")
# a request to the house anywhere in the sentence, even with a name in it: "Marco vuole sentire la musica",
# "Marco is hungry, light the barbecue" (not after a question word: "cosa vuole ascoltare Marco?")
REQUEST = re.compile(r"\b(accendi|accendete|accendiamo|spegni|spegnete|spegniamo|metti|mettete|mettiamo|fai|facciamo|"
                     r"fate|apri|chiudi|alza|abbassa|vuole sentire|vuole ascoltare|vogliono sentire|turn on|turn off|"
                     r"switch on|switch off|put on|light (the|up|a)|let s|lets|wants to hear|wants to listen)\b")
POLITE = re.compile(r"\b(puoi|potresti|potete|can you|could you|would you) (mettere|accendere|spegnere|fare|alzare|"
                    r"abbassare|suonare|put|turn|light|play|start|switch|make)\b")
QUESTION_START = re.compile(r"^(cosa|che|quale|qual|quali|chi|come|dove|dov|quanto|quanti|quanta|quante|quando|perche|"
                            r"di che|a che|per che|what|which|who|how|where|when|why|does|do|did|is|are|has|have)\b")
FOR_SOMEONE = re.compile(r"^(\w+ ){1,4}(per|for)$")      # "musica per Marco", once the name is gone
LIKES = "likes"        # the topic of "what does Giulia like?": the facts that say what somebody likes


def _without(text: str, names: Iterable[str]) -> str:
    """The sentence, normalized, without the names of the characters ("Viola" is a colour, "Brown" too), also a
    name of two words heard by one of them ("le misure brown" for Mister Brown is no question about a colour)."""
    from .intents import find_names
    names = [n for n in names if n]
    t = f" {normalize(text)} "
    for n in sorted({normalize(n) for n in names}, key=len, reverse=True):
        t = t.replace(f" {n} ", " ")
    for n in find_names(normalize(text), names):
        if len(normalize(n).split()) > 1:
            for w in normalize(n).split():
                t = t.replace(f" {w} ", " ")
    return " ".join(t.split())


def _job_said(text: str, names: Iterable[str]) -> bool:
    """"Marco fa il dottore?", "is Anna a nurse?": what is left without the name reads as a job."""
    from .stories import is_job
    rest = text
    for n in sorted((n for n in names if n), key=len, reverse=True):
        rest = re.sub(rf"\b{re.escape(n)}\b", " ", rest, flags=re.I)
    rest = re.sub(r"[^\w'’ ]+", " ", rest)
    return is_job(re.sub(r"\s+", " ", rest).strip())


def topics(text: str, names: Iterable[str] = ()) -> list[str]:
    """The topics of a sentence, most specific first; the names of the characters do not count."""
    t = _without(text, names)
    found = [topic for topic, rx in _TOPIC_RE if rx.search(t)]
    if not found and _job_said(text, names):      # only then: "is an early riser" is not a job
        found = ["job"]
    return found


def liking(text: str, names: Iterable[str] = ()) -> bool:
    return bool(LIKING.search(_without(text, names)))


def is_request(text: str, names: Iterable[str] = ()) -> bool:
    """The sentence asks the house for something, even if it names a character ("puoi mettere la musica
    preferita di Anna?", "musica per Marco", "Marco is hungry, light the barbecue")."""
    t = normalize(text)
    if COMMAND.search(t) or POLITE.search(t):
        return True
    return not QUESTION_START.match(t) and bool(REQUEST.search(t) or FOR_SOMEONE.match(_without(text, names)))


def asks_about(text: str, names: Iterable[str] = ()) -> bool:
    """The sentence asks something about a character (its tastes, its job, where it comes from...), and asks
    the house for nothing."""
    return not is_request(text, names) and bool(topics(text, names) or liking(text, names))


def question_topic(text: str, names: Iterable[str] = ()) -> str | None:
    """What a question about a character is about by its keywords: a topic, LIKES, or None."""
    found = topics(text, names)
    return found[0] if found else LIKES if liking(text, names) else None


# ------------------------------------------------------------------ answers that become facts
# The questions of chatty mode whose answer says something lasting about the character (chatter.QUESTIONS
# by id), and the line each answer becomes in each language. "open" questions take the answer as it was
# said ({v}); "options" follow the options of the question in order; "yes"/"no" the answer to a yes/no
# question; "colour" one line per colour of intents.COLORS. Every line agrees with any name.
_COLOUR_IT = {"red": "il rosso", "green": "il verde", "blue": "il blu", "yellow": "il giallo",
              "orange": "l'arancione", "purple": "il viola", "pink": "il rosa", "white": "il bianco",
              "cyan": "l'azzurro"}
ANSWER_FACTS: dict[str, dict[str, Any]] = {
    "k-dish": {"topic": "food", "open": ("adora mangiare {v}", "loves eating {v}")},
    "a-from": {"topic": "origin", "open": ("viene {v}", "comes from {v}")},
    "k-cook": {"topic": "food", "options": [
        ("preferisce la pizza alla pasta", "prefers pizza to pasta"),
        ("preferisce la pasta alla pizza", "prefers pasta to pizza")]},
    "l-sofa": {"topic": "seat", "options": [
        ("preferisce il divano alla poltrona", "prefers the sofa to the armchair"),
        ("preferisce la poltrona al divano", "prefers the armchair to the sofa")]},
    "g-trip": {"topic": "travel", "options": [
        ("preferisce il mare alla montagna", "prefers the seaside to the mountains"),
        ("preferisce la montagna al mare", "prefers the mountains to the seaside")]},
    "a-morning": {"topic": "sleep", "options": [
        ("è più da mattina che da sera", "is more of a morning person"),
        ("è più da sera che da mattina", "is more of an evening person")]},
    "a-colour": {"topic": "colour", "colour": {
        **{c: (f"ha come colore preferito {it}", f"loves the colour {c}") for c, it in _COLOUR_IT.items()},
        "warm": ("ama la luce calda", "loves warm light")}},
    "a-house": {"topic": "home", "yes": ("adora questa casa", "loves this house"),
                "no": ("non ama molto questa casa", "is not too fond of this house")},
    "o-garden": {"topic": "home", "yes": ("adora il giardino", "loves the garden"),
                 "no": ("non ama molto il giardino", "is not too fond of the garden")},
    # the answers the house acts on: a party for who loves dancing, the barbecue for who loves it
    "a-dance": {"topic": "music", "yes": ("ama ballare", "loves dancing"),
                "no": ("non ama ballare", "is not fond of dancing")},
    "a-grill": {"topic": "food", "yes": ("adora le grigliate", "loves barbecues"),
                "no": ("non ama le grigliate", "is not fond of barbecues")},
}
LANGS = ("it", "en")
MAX_WORDS = {"k-dish": 6, "a-from": 5}       # a longer answer is more likely a sentence the house misheard

# fillers around an answer said freely ("beh, direi la pizza, grazie"), on lower case text with its accents
# and apostrophes
_FILLERS = {
    "it": r"allora|beh|be|mah|ma|eh|ehm|uhm|ah|oh|dunque|senti|guarda|ok|okay|s[iì]|certo|sicuramente|direi|"
          r"penso|credo|secondo me|forse|ovviamente|naturalmente|di sicuro|per me|io|a me|sempre|tanto|molto|"
          r"che|e|hmm|mmm|mm|hm",
    "en": r"well|um|uh|er|oh|ah|hmm|mmm|mm|hm|so|ok|okay|yes|yeah|i think|i guess|i'?d say|i d say|probably|"
          r"definitely|maybe|"
          r"of course|actually|really|always",
}
_LEADS = {
    "k-dish": {"it": r"(il )?mio piatto preferito( [eè]| sono)?|il mio preferito( [eè])?|"
                     r"il piatto che preferisco( [eè])?|mi piace( tanto| molto| di pi[uù])?|"
                     r"mi piacciono( tanto| molto| di pi[uù])?|piace( tanto| molto| di pi[uù])?|piacciono|adoro|amo|"
                     r"preferisco|vado (matto|matta|pazzo|pazza) per|[eè]",
               "en": r"my favou?rite (dish |food |meal )?is|my favou?rite'?s|my favou?rite s|"
                     r"i (really )?(love|like|adore|prefer)|it'?s|it s|it is|i'?d have|i d have|i'?ll have|"
                     r"i ll have"},
    "a-from": {"it": r"(io )?vengo|(io )?sono (nato|nata)|(io )?sono|(io )?abito|(io )?vivo|nato|nata|abito|vivo",
               "en": r"i'?m|i m|i am|i come|i was born|i live|we'?re|we re|we are|we come|born|living"},
}
_TRAILERS = r"grazie|credo|direi|penso|ovviamente|naturalmente|secondo me|of course|i think|thanks|thank you|obviously"
_NOTHING = re.compile(r"^(no|non|niente|nulla|nessuno|nessuna|boh|mah|non lo so|non so|nothing|none|nope|"
                      r"i don t know|don t know|dunno|not sure|dipende|depends)\b")
# a value with these is a sentence about the speaker, not a dish or a place ("sono vegetariano", "mi chiamo
# Giulia", "i don't eat meat"): no fact
_NOT_A_VALUE = re.compile(r"\b(no|non|ne|niente|nulla|mai|sono|sei|siamo|mi|io|me|mio|mia|miei|mie|ti|tu|te|tuo|tua|"
                          r"chiamo|mangio|bevo|piace|piacciono|voglio|vorrei|odio|detesto|faccio|ho|abbiamo|"
                          r"allergic\w*|intolleran\w*|vegetarian\w*|vegan\w*|i|im|me|my|mine|you|your|not|never|don|"
                          r"dont|t|hate|eat|like|love|am|name|nothing)\b")
# for "da dove vieni?": the name of a people is not a place ("sono italiana" is no "viene da Italiana")
_PEOPLE = re.compile(r"^((italian|roman|napoletan|sicilian|toscan|venezian|fiorentin|lombard|palermitan|friulan|"
                     r"emilian|marchigian|lucan|romagnol|sard|venet|american|australian|brasilian|argentin|messican|"
                     r"egizian|indian|marocchin|tedesc|spagnol|svizzer|russ|grec|turc|polacc|rumen)[oaie]|"
                     r"(torines|milanes|genoves|bolognes|piemontes|pugli?es|calabres|abruzzes|bares|ingles|frances|"
                     r"olandes|portoghes|giappones|cines|londines|irlandes|scozzes|canades|albanes|ligur)[ei]|"
                     r"english|british|italian|french|german|spanish|american|irish|scottish|welsh|swiss|chinese|"
                     r"japanese|dutch|londoner|canadian|australian|mexican|brazilian|argentinian|portuguese|greek|"
                     r"turkish|polish|russian|indian)$")
_PLACE_SMALL = {"di", "del", "della", "dei", "delle", "de", "da", "e", "in", "sul", "sulla", "al", "alla", "of",
                "the", "and", "upon", "on"}
_IT_FROM = r"(da|dal|dallo|dalla|dall|dai|dagli|dalle)"


def _plain(text: str) -> str:
    """Lower case, spaces normalized, apostrophes kept (the value is said again as it was heard)."""
    text = re.sub(r"[’`]", "'", text.lower())
    text = re.sub(r"[^\w' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strip(text: str, pattern: str, at_end: bool = False) -> str:
    rx = re.compile(rf"\s*\b({pattern})$" if at_end else rf"^({pattern})\b\s*")
    while True:
        new = rx.sub("", text, count=1).strip()
        if new == text:
            return text
        text = new


def _place(words: str) -> str:
    """Capital letters for the name of a place, "da" and the like stay small: "da Reggio Emilia"."""
    out = []
    for w in words.split():
        if w in _PLACE_SMALL or re.fullmatch(_IT_FROM, w):
            out.append(w)
        else:
            out.append("'".join(p[:1].upper() + p[1:] if not re.fullmatch(_IT_FROM, p) else p for p in w.split("'")))
    return " ".join(out)


def answer_value(qid: str, text: str, lang: str) -> str | None:
    """The answer to an open question as it can follow the template of its fact, or None if there is none
    (a "boh", a "no", only fillers, or a long sentence the house would rather not repeat)."""
    t = _plain(text)
    if not t or _NOTHING.search(normalize(t)):
        return None
    lead = _LEADS.get(qid, {}).get(lang, "")
    for _ in range(3):
        t = _strip(t, _FILLERS[lang])
        if lead:
            t = _strip(t, lead)
    t = _strip(t, _TRAILERS + "|" + _FILLERS[lang], at_end=True)
    if not t or not re.search(r"[^\W\d_]", t) or _NOTHING.search(normalize(t)) or _NOT_A_VALUE.search(normalize(t)):
        return None
    if len(t.split()) > MAX_WORDS.get(qid, 5):
        return None
    if qid == "a-from":
        if not re.match(rf"(di|a|in|from|{_IT_FROM})\b|dall'", t) and len(t.split()) == 1 and _PEOPLE.match(t):
            return None
        t = re.sub(r"^(di|a|in|from)\s+", "", t)
        if lang == "it" and not re.match(rf"{_IT_FROM}\b|dall'", t):
            t = "da " + t
        t = _place(t)
    return t


def answer_line(qid: str, outcome: str, text: str, lang: str) -> str | None:
    """The fact an answer to question `qid` becomes, in `lang`: None when the question tells nothing lasting
    or the answer is not clear. `outcome` is what chatter.react made of it ("option 1", "colour blue",
    "yes", "no", "answered")."""
    spec = ANSWER_FACTS.get(qid)
    if spec is None or lang not in LANGS:
        return None
    k = LANGS.index(lang)
    if "open" in spec:
        if outcome != "answered":
            return None
        value = answer_value(qid, text, lang)
        return spec["open"][k].replace("{v}", value) if value else None
    if "options" in spec and outcome.startswith("option "):
        i = int(outcome.split()[1])
        return spec["options"][i][k] if i < len(spec["options"]) else None
    if "colour" in spec and outcome.startswith("colour "):
        pair = spec["colour"].get(outcome.split()[1])
        return pair[k] if pair else None
    if outcome in ("yes", "no") and outcome in spec:
        return spec[outcome][k]
    return None


# what an answer to "tu lo sai?" becomes, by the topic of the question the house could not answer: a fact that reads
# after the name, like the ones typed in the web app ("ama il gelato"); food, origin and colour take the lines of the
# questions of chatty mode, so that a newer answer takes the place of the older one
LEARN_TEMPLATES = {
    LIKES: ("ama {v}", "loves {v}"),
    "drink": ("beve volentieri {v}", "likes drinking {v}"),
    "music": ("ascolta {v}", "listens to {v}"),
    "sport": ("pratica {v}", "plays {v}"),
    "job": ("fa {v}", "works as {v}"),
    "fear": ("ha paura di {v}", "is afraid of {v}"),
    "hobby": ("nel tempo libero ama {v}", "in the free time loves {v}"),
    "travel": ("va in vacanza {v}", "goes on holiday {v}"),
    "animals": ("ha {v}", "has {v}"),
    "family": ("ha {v}", "has {v}"),
    "age": ("ha {v} anni", "is {v} years old"),
    "seat": ("preferisce sedersi {v}", "prefers sitting {v}"),
}
# how somebody says it of the character, before the answer itself ("le piace il gelato", "lei ama ballare")
_THIRD = {
    "it": r"(lei|lui|loro|a lei|a lui|le|gli)|(si chiama|ama|amano|adora|adorano|preferisce|piace|piacciono|mangia|"
          r"beve|ascolta|pratica|gioca a|gioca|fa|lavora come|lavora|viene|vive|abita|ha paura di|ha paura|ha|[eè])",
    "en": r"(she|he|they|her|him)|(loves|likes|adores|prefers|eats|drinks|listens to|plays|works as|is afraid of|"
          r"comes from|lives in|has|is|'s)",
}


def nothing_told(text: str) -> bool:
    """"Non lo so", "boh", "no": an answer that tells nothing."""
    return bool(_NOTHING.search(normalize(_strip(_plain(text), _FILLERS["it"] + "|" + _FILLERS["en"]))))


def learned_line(topic: str | None, text: str, names: Iterable[str], lang: str) -> tuple[str | None, str] | None:
    """The fact an answer to a question the house could not answer becomes, as (question of chatty mode or None,
    line); None when the answer tells nothing ("non lo so") or no line fits the topic (the answer is then kept as it
    is, see knowledge.py). The character it is about is left out: "Rossellina ama il gelato" is "ama il gelato"."""
    from .intents import find_color
    if lang not in LANGS:
        return None
    k = LANGS.index(lang)
    t = _plain(text)
    for n in sorted((n for n in names if n), key=len, reverse=True):
        t = re.sub(rf"(?i)\b{re.escape(n)}\b", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" ,.;:!")
    if not t or _NOTHING.search(normalize(t)):
        return None
    if topic == "colour":
        colour = find_color(normalize(t))
        return ("a-colour", ANSWER_FACTS["a-colour"]["colour"][colour][k]) if colour in ANSWER_FACTS["a-colour"]["colour"] \
            else None
    if topic in ("food", "origin"):
        qid = "k-dish" if topic == "food" else "a-from"
        t = _strip(t, _THIRD[lang])
        line = answer_line(qid, "answered", t, lang)
        return (qid, line) if line else None
    template = LEARN_TEMPLATES.get(topic or "")
    if template is None:
        return None
    if topic == "sport" and lang == "it" and re.search(r"\bgioca a\b", t, re.I):
        template = ("gioca a {v}", template[1])            # "gioca a calcio", not "pratica calcio"
    for _ in range(3):
        t = _strip(t, _FILLERS[lang])
        t = _strip(t, _THIRD[lang])
    t = _strip(t, _TRAILERS + "|" + _FILLERS[lang], at_end=True)
    if not t or not re.search(r"[^\W\d_]|\d", t) or _NOTHING.search(normalize(t)) or len(t.split()) > 8:
        return None
    if topic == "job" and lang == "it" and not re.match(r"(il|lo|la|l'|i|gli|le|un|una|uno)\b", t, re.I):
        return None, f"lavora come {t}"
    if topic == "age":
        from .intents import EN_NUMBERS, IT_NUM
        n = re.search(r"\d+", t)
        words = normalize(t).replace(" anni", "").replace(" years old", "").split()
        if n is not None:
            t = n.group(0)
        elif words and all(w in IT_NUM or w in EN_NUMBERS or w == "e" for w in words):
            t = " ".join(words)                                 # "trenta": "ha trenta anni"
        else:
            return None, ("ha " + t) if lang == "it" else ("is " + t)
    if topic == "fear" and lang == "it":
        if re.match(r"(di|dei|del|della|delle|degli|dello|d')\b", t, re.I):
            return None, f"ha paura {t}"                      # "dei ragni": "ha paura dei ragni"
        art = re.match(r"(il|lo|la|i|gli|le|l')\s*", t, re.I)
        if art:                                               # "i ragni": "ha paura dei ragni"
            di = {"il": "del", "lo": "dello", "la": "della", "i": "dei", "gli": "degli", "le": "delle", "l'": "dell'"}
            rest = t[art.end():]
            return None, f"ha paura {di[art.group(1).lower()]}{'' if di[art.group(1).lower()].endswith(chr(39)) else ' '}{rest}"
    return None, template[k].replace("{v}", t)


def told(lines: Iterable[str], qid: str) -> Any:
    """What the facts say as the answer to question `qid` ("yes", "no", an option, a colour), the latest line
    winning; None if they say nothing about it."""
    out = None
    for line in lines:
        got = read(line)
        if got and got[0] == qid:
            out = got[2] if got[2] is not None else got[3]
    return out


def favourite_colour(lines: Iterable[str]) -> str | None:
    """The favourite colour told, as a colour of intents.COLORS ("red", "warm"...), or None: from an answer to "qual è
    il tuo colore preferito?", or from a line typed in the web app that talks of a favourite colour ("Il suo colore
    preferito è il rosso", "loves the colour blue") or loves one ("ama il verde")."""
    from .intents import find_color
    lines = list(lines)
    said = told(lines, "a-colour")
    if said:
        return said
    for line in reversed(lines):
        t = normalize(line)
        if re.search(r"\bcolor\w*|\bcolour\w*", t) or re.match(r"^(ama|adora|loves|likes) (il |l |the )?\w+$", t):
            colour = find_color(t)
            if colour:
                return colour
    return None


# what a question about a character asks, beyond its keywords: the words it shares with a fact ("Marco legge i
# fumetti?" and "ha un debole per i fumetti"), compared by their first five letters; these words say nothing
_PLAIN = set("""cosa come dove quando quale quali chi perche quanto quanti quanta quante che non piu molto poco anche
ancora sempre mai gia sono sei siamo siete essere stato stata hanno avere fare fatto fanno dice dire detto sapere sai
sa piace piacciono piaceva ama amano adora preferisce vuole vorrebbe puoi posso dimmi raccontami parlami qualcosa
tutto tutti quello questa questo quella della delle dello degli nella nelle sulla sulle alla alle allo agli dalla
dalle con per tra fra suo sua suoi sue mio mia tuo tua loro what which does doing about would could should have
with from that this they them their there where when your like likes love loves tell know something""".split())


def overlap(text: str, lines: list[str], names: Iterable[str] = (), most: int = 2) -> list[int]:
    """The facts (indices, latest first) that share a word with the question: what keywords do not tell, found at
    once without the language model."""
    def stems(t: str) -> set[str]:
        return {w[:5] for w in _without(t, names).split() if len(w) >= 4 and w not in _PLAIN}
    asked = stems(text)
    if not asked:
        return []
    hits = [i for i, f in enumerate(lines) if asked & stems(f)]
    return list(reversed(hits))[:most]


# ------------------------------------------------------------------ reading a line back
def _open_rx(template: str) -> re.Pattern:
    head = re.escape(template.split("{v}")[0].strip())
    return re.compile(rf"^{head}\s+(?P<v>.+)$", re.I)


_READ: list[tuple[str, str, Any, Any]] = []     # (question, language, option or None, pattern or line)
for _qid, _spec in ANSWER_FACTS.items():
    for _k, _lang in enumerate(LANGS):
        if "open" in _spec:
            _READ.append((_qid, _lang, None, _open_rx(_spec["open"][_k])))
        for _i, _pair in enumerate(_spec.get("options", [])):
            _READ.append((_qid, _lang, _i, _pair[_k]))
        for _c, _pair in _spec.get("colour", {}).items():
            _READ.append((_qid, _lang, _c, _pair[_k]))
        for _yn in ("yes", "no"):
            if _yn in _spec:
                _READ.append((_qid, _lang, _yn, _spec[_yn][_k]))


def read(line: str) -> tuple[str, str, Any, str | None] | None:
    """(question, language, option, value) of a line made from an answer, None for any other line."""
    line = line.strip().rstrip(".")
    low = line.casefold()
    for qid, lang, option, pattern in _READ:
        if isinstance(pattern, str):
            if low == pattern.casefold():
                return qid, lang, option, None
            continue
        m = pattern.match(line)
        if m is None:
            continue
        value = m.group("v")
        if qid == "a-from" and lang == "it" and not re.match(rf"{_IT_FROM}\b|dall'", value, re.I):
            continue                      # "viene spesso a trovarci" is not where somebody comes from
        if qid == "a-from" and _place(value) != value:
            continue                      # a place is written "da Reggio Emilia": "viene da una famiglia di
                                          # musicisti" was typed by somebody, and stays as it is
        if len(value.split()) > MAX_WORDS.get(qid, 5) + 1:
            continue                      # longer than any answer kept
        return qid, lang, option, value
    return None


def line_lang(line: str) -> str | None:
    """The language of a line made from an answer (None for any other line)."""
    got = read(line)
    return got[1] if got else None


def _value_in(value: str, src: str, lang: str, qid: str) -> str:
    """An open answer said in one language, ready for the template of the other."""
    if qid == "a-from":
        if src == "it":
            value = re.sub(rf"^{_IT_FROM}\s+|^dall'", "", value, flags=re.I)
        return value if lang == "en" else "da " + value
    if src == "it":
        return re.sub(r"^(il|lo|la|i|gli|le)\s+|^l'", "", value, flags=re.I)
    return re.sub(r"^(a|an|the)\s+", "", value, flags=re.I)


def translated(line: str, lang: str) -> str | None:
    """A line made from an answer, in `lang` (itself if it is already in it); None for any other line."""
    got = read(line)
    if got is None:
        return None
    qid, src, option, value = got
    if src == lang:
        return line.strip().rstrip(".")
    spec, k = ANSWER_FACTS[qid], LANGS.index(lang)
    if value is not None:
        return spec["open"][k].replace("{v}", _value_in(value, src, lang, qid))
    if isinstance(option, int):
        return spec["options"][option][k]
    if option in ("yes", "no"):
        return spec[option][k]
    return spec["colour"][option][k]


def put(facts: list[str], qid: str, line: str, limit: int) -> list[str] | None:
    """The facts with the answer to question `qid`: it takes the place of the old answer to the same question,
    in either language; when the list is full the oldest answer makes room, never a line somebody typed
    (None: there is no room)."""
    kept = [f for f in facts if (read(f) or ("",))[0] != qid]
    kept.append(line)
    while len(kept) > limit:
        oldest = next((i for i, f in enumerate(kept[:-1]) if read(f)), None)
        if oldest is None:
            return None
        kept.pop(oldest)
    return kept


# ------------------------------------------------------------------ which facts answer a question
def fact_topics(line: str, names: Iterable[str] = ()) -> set[str]:
    """What a fact is about: the topic of its question if it was an answer, its keywords, a job, a liking.
    The names of the characters do not count ("vive con Bianca" says nothing about a colour)."""
    from .stories import is_job
    got = read(line)
    out = set(topics(line, names))
    if got:
        out.add(ANSWER_FACTS[got[0]]["topic"])
    if is_job(line):
        out.add("job")
    if LIKING.search(_without(line, names)):
        out.add(LIKES)
    return out


def needs_model(line: str, names: Iterable[str] = ()) -> bool:
    """Nothing tells what the fact is about but the language model ("ha un debole per i fumetti")."""
    return not fact_topics(line, names) - {LIKES}


def select(topic: str | None, facts: list[str], known: dict[str, str] | None = None, most: int = 2,
           names: Iterable[str] = ()) -> list[int]:
    """The facts (indices) about `topic`, the latest first. `known` holds the topics the language model told
    for the facts no keyword describes (by normalized text)."""
    if not topic:
        return []
    known = known or {}
    names = list(names)
    hits = []
    for i, f in enumerate(facts):
        tags = fact_topics(f, names)
        if not tags - {LIKES} and known.get(normalize(f)):
            tags.add(known[normalize(f)])
        if topic in tags:
            hits.append(i)
    return list(reversed(hits))[:most]


# what the house says: the facts after the name, or that it does not know
KNOWN = [("So che {name} {fact}.", "I know that {name} {fact}."),
         ("Mi risulta che {name} {fact}.", "As far as I know, {name} {fact}."),
         ("Ecco cosa so: {name} {fact}.", "Here's what I know: {name} {fact}.")]
UNKNOWN = [("Non lo so: {name} non me l'ha ancora detto.", "I don't know: {name} hasn't told me yet."),
           ("Di {name} questo non lo so ancora.", "I don't know that about {name} yet."),
           ("Ah, {name} non me l'ha mai detto.", "Oh, {name} has never told me.")]
NOTED = ("Me lo segno: {name} {fact}.", "I'll remember that: {name} {fact}.")


# ------------------------------------------------------------------ the language model
SYSTEM = """Tell what a sentence about a character of a model house is about, with one topic.
Topics: food (eating, dishes, cooking), drink, colour, music (songs, instruments, listening), sport (playing, teams), job (work, school, profession), fear, hobby (free time, collections), travel (sea, mountains, holidays), seat (sofa, armchair), origin (where somebody comes from or lives), animals (pets), family, age, home (this house, the garden), sleep (mornings, evenings, waking up), likes (what somebody likes, no topic above), other.
Sentences may be questions or facts, in Italian or English, and may contain recognition errors."""
LABELS = TOPIC_IDS + [LIKES, "other"]

_EXAMPLES = [
    ("cosa mangia volentieri Sara", "food"), ("what does Tom eat for breakfast", "food"),
    ("adora le lasagne", "food"), ("loves chocolate cake", "food"), ("che cosa preparo a cena per Luca", "food"),
    ("Pia è golosa di dolci?", "food"), ("does Ben like spicy food", "food"),
    ("ha un debole per il cioccolato", "food"), ("beve solo tè verde", "drink"), ("what does Ada drink", "drink"),
    ("Ugo prende il caffè?", "drink"), ("che colore piace a Ugo", "colour"),
    ("ha come colore preferito il verde", "colour"), ("which colour does Kim prefer", "colour"),
    ("Ivo ama il giallo?", "colour"), ("che canzoni piacciono a Bea", "music"), ("ama il rock", "music"),
    ("plays the violin", "music"), ("does Sam listen to the radio", "music"),
    ("Leo canta sotto la doccia?", "music"), ("Nina va all'opera?", "music"), ("gioca a calcio il sabato", "sport"),
    ("per che squadra tifa Ivo", "sport"), ("does Kim swim", "sport"), ("Ada è sportiva?", "sport"),
    ("va in palestra tutti i giorni", "sport"), ("does Joe go running", "sport"), ("che mestiere fa Rita", "job"),
    ("insegna matematica", "job"), ("is a nurse", "job"), ("Pia va in ufficio?", "job"), ("fa il pompiere", "job"),
    ("Ugo lavora in banca?", "job"), ("di cosa ha paura Dino", "fear"), ("is scared of the dark", "fear"),
    ("odia i ragni", "fear"), ("Tea si spaventa facilmente?", "fear"), ("does Bob fear heights", "fear"),
    ("cosa fa Gino nel tempo libero", "hobby"), ("colleziona conchiglie", "hobby"),
    ("what are Ann's hobbies", "hobby"), ("Rino fa i puzzle?", "hobby"), ("loves reading comics", "hobby"),
    ("dove va in vacanza Nora", "travel"), ("preferisce la spiaggia", "travel"),
    ("Sara ama il mare o la montagna?", "travel"), ("does Liz travel a lot", "travel"),
    ("has been to Paris twice", "travel"), ("si siede sempre sulla poltrona", "seat"),
    ("where does Bob like to sit", "seat"), ("Ada preferisce il divano?", "seat"),
    ("does Kim like the armchair", "seat"), ("Ugo è napoletano?", "origin"), ("viene da Bari", "origin"),
    ("where was Liz born", "origin"), ("lives in Leeds", "origin"), ("is Sam Scottish", "origin"),
    ("ha un cane?", "animals"), ("adora i gatti", "animals"), ("does Max have a pet", "animals"),
    ("Ivo ha fratelli?", "family"), ("is married", "family"), ("ha due figlie", "family"),
    ("quanti anni ha Lia", "age"), ("how old is Dan", "age"), ("a Mia piace la casa", "home"),
    ("does Joe like the garden", "home"), ("si trova bene in questa casa", "home"),
    ("Ezio si alza presto?", "sleep"), ("è un nottambulo", "sleep"), ("is Fred a morning person", "sleep"),
    ("Leo è un dormiglione?", "sleep"), ("goes to bed early", "sleep"), ("cosa piace a Zoe", "likes"),
    ("what does Amy love", "likes"), ("dov'è Paolo", "other"), ("che ore sono", "other"),
    ("accendi la luce", "other"), ("Paolo è in cucina?", "other"), ("is Tom in the garden", "other"),
    ("ciao come stai", "other"), ("Ugo è simpatico?", "other"), ("Ada porta gli occhiali?", "other"),
    ("has blue eyes", "other"), ("is Tom tall", "other"),
]


def _mixed(examples: list[tuple[str, str]]) -> list[tuple[str, str]]:
    # a fixed order, never ending on "other": a small model tends to repeat the last answers it saw
    out = list(examples)
    random.Random(11).shuffle(out)
    while out[-1][1] == "other":
        out.insert(0, out.pop())
    return out


EXAMPLES = _mixed(_EXAMPLES)
MIN_CONFIDENCE = 0.4       # below this the topic was a guess: "I don't know" is better than a wrong fact
TAG_CONFIDENCE = 0.9       # the topic of a fact is kept for good: a fact the model is less sure of stays untagged


def _user(sentence: str) -> str:
    return f"Sentence: {sentence}"


def messages(sentence: str) -> list[dict[str, str]]:
    out = [{"role": "system", "content": SYSTEM}]
    for said, topic in EXAMPLES:
        out.append({"role": "user", "content": _user(said)})
        out.append({"role": "assistant", "content": topic})
    out.append({"role": "user", "content": _user(sentence)})
    return out


GRAMMAR = "root ::= " + " | ".join(json.dumps(label) for label in LABELS)


def parse_topic(text: str, confidence: float = 1.0, least: float = MIN_CONFIDENCE) -> str | None:
    """The topic the model gave; None for "other" or a guess (less sure than `least`)."""
    word = text.strip().split()[0] if text.strip() else ""
    if word not in LABELS or word == "other" or confidence < least:
        return None
    return word
