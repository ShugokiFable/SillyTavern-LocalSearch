# SillyTavern: local model + free web search

Two things SillyTavern can do but does not do out of the box, wired up and
measured rather than assumed:

1. **Free web search** with no API key and no account — a small local endpoint
   that speaks the shape SillyTavern already knows how to read.
2. **A local LM Studio model as a selectable API**, including the two
   non-obvious steps that otherwise make it look broken.

Everything runs on your own machine. Nothing leaves it except the search query.

---

## 1. Free web search

### Why this is needed

SillyTavern's [Web Search extension](https://github.com/SillyTavern/Extension-WebSearch)
ships six sources and **none of them is both free and self-contained**:

| Source | What it wants |
|---|---|
| SerpApi, Tavily, Serper, Z.AI | an API key |
| KoboldCpp | a running KoboldCpp with websearch |
| SearXNG | the URL of a SearXNG instance |

SearXNG is the only keyless one, so the usual advice is "point it at a public
instance". Measured, that does not work:

```
https://searx.be           HTTP 200  -> captcha page, 0 results
https://baresearch.org     HTTP 200  -> 0 results
https://priv.au            HTTP 429
https://searxng.site       HTTP 429
https://search.inetol.net  HTTP 429
```

Self-hosting real SearXNG normally means Docker.

So `local_search.py` serves the **SearXNG shape** that SillyTavern already
parses, backed by DuckDuckGo through the `ddgs` package. No key, no account, no
container.

### Setup

```bash
python -m pip install ddgs
```

Then run `Start-LocalSearch.bat` (or `python local_search.py`) and leave it
open. In SillyTavern:

**Extensions → Web Search**
- Source: **SearXNG**
- SearXNG URL: `http://127.0.0.1:18888`

Test with a trigger phrase — "what is the current version of Rust" — or wrap
the query in backticks, which forces a search regardless of phrasing.

### Wanting it silent

The `.bat` keeps a console window open on purpose, so it is obvious when search
is on. To run it without a window:

```bat
start "" pythonw local_search.py --port 18888
```

`pythonw` has no console, so nothing then tells you it is running. Check with
`curl http://127.0.0.1:18888/`.

### What it actually implements

`Extension-WebSearch` 1.2.0 parses exactly four things out of the returned
HTML, and only these are produced:

```
#urls p.content                        -> result snippets
#urls .url_header, #urls .url_wrapper  -> result links (href attribute)
#urls .detail img[data-src]            -> image results (categories=images)
.infobox p / .infobox a                -> optional; not emitted
```

SillyTavern's server also GETs the base URL before searching and, if the page
links a `/client*.css`, fetches that too. Both are answered, so the request
flow matches a real instance rather than relying on a lucky shortcut.

`test_local_search.py` asserts that contract against a live instance of the
server. Run it after changing anything:

```bash
python test_local_search.py
```

### Limits worth knowing

- **It is DuckDuckGo.** Result quality and rate limits are theirs. A burst of
  searches can start returning nothing; wait a minute.
- **Snippets only, by default.** SillyTavern's *Visit* option fetches the linked
  pages for real content. It is off by default because it costs several seconds
  per message. Turn it on in the extension panel if snippets are too thin.
- **Loopback only.** There is no authentication. Do not bind it to `0.0.0.0`.
- A failed upstream returns an empty result page rather than an error, so a
  rate-limited search degrades to "no results" instead of breaking generation.

---

## 2. LM Studio as a SillyTavern API

Use **Chat Completion → Custom (OpenAI-compatible)**:

| Field | Value |
|---|---|
| Custom Endpoint | `http://127.0.0.1:1234/v1` |
| Custom API Key | any non-empty string |
| Model | picked from the dropdown once connected |

Start the server first — `lms server start`, or the toggle in the LM Studio
app. There is no CLI flag to auto-start it; check `lms server start --help` if
you expect one.

### The API key is required by SillyTavern, not by LM Studio

LM Studio ignores it completely. Verified both ways: `/v1/models` returns the
model list with a deliberately bogus bearer token **and** with no
`Authorization` header at all.

SillyTavern still refuses to enumerate models without one —
`src/endpoints/backends/chat-completions.js`:

```js
if (!apiKey && !request.body.reverse_proxy) {
    return statusResponse.status(400).send({ error: true });
}
```

The symptom is an empty model dropdown and a bare `{"error":true}`, which reads
like a connection problem and is not one. Put any word in the box.

### Reasoning models return nothing if the response length is small

This one costs an afternoon if you do not know it. With a reasoning model, the
thinking tokens come out of the **same budget** as the reply. Measured on a
Qwen3.6-35B-A3B build through SillyTavern:

| Response length | Result |
|---|---|
| 40 tokens | `''` — all 40 spent on reasoning, empty message |
| 600 tokens | the actual reply; 191 of 203 completion tokens were reasoning |

So a short Response Length does not give you a short answer, it gives you *no*
answer. Set it to 512 at the very minimum, and 1024+ in practice.

### While you are there

If LM Studio also serves an embedding model, SillyTavern's **Vectors**
extension can point at the same endpoint for local RAG over your chats and
lorebooks — same URL, same non-secret key.

---

## Note for Hermes users

If you drive the same LM Studio model from
[Hermes](https://github.com/NousResearch/hermes-agent), **load it at 65,536
context or higher**. Hermes hard-refuses any model whose window is under 64,000
tokens and raises before the first turn. LM Studio commonly saves 32,768, which
is fine for SillyTavern and a non-starter there.

## License

MIT — see `LICENSE`. The Web Search extension it feeds is a separate project
under AGPL-3.0 and is not redistributed here.
