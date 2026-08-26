# SillyTavern: local model + free web search

Two things SillyTavern can do but does not do out of the box, wired up and
measured rather than assumed:

1. **Free web search** with no API key and no account — a small local endpoint
   that speaks the shape SillyTavern already knows how to read.
2. **A local LM Studio model as a selectable API**, including the three
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

### Starting it automatically with SillyTavern

`st-plugin/` is a SillyTavern **server plugin**. SillyTavern starts the search
endpoint when it boots and kills it when it shuts down, so there is no window to
remember and nothing to leave running afterwards.

It needs `enableServerPlugins: true` in SillyTavern's `config.yaml`, then a
junction from SillyTavern's `plugins` folder to `st-plugin`:

```bat
mklink /J "C:\path\to\SillyTavern\plugins\local-search" "C:\path\to\SillyTavern-LocalSearch\st-plugin"
```

A junction rather than a copy, so pulling this repo updates the plugin with no
second step. SillyTavern's plugin auto-update ignores it, because a junction to
a subdirectory is not a Git repository root.

On the next start SillyTavern logs:

```
Initializing plugin from plugins\local-search\index.mjs
[local-search] started on http://127.0.0.1:18888 (pid 12345)
```

The plugin probes the port first, so running `Start-LocalSearch.bat` by hand
still works — SillyTavern sees the endpoint is up and does not start a second
copy. If no Python on `PATH` can `import ddgs` it says so and starts nothing,
instead of failing silently at the first search.

Override the defaults with the `LOCAL_SEARCH_PORT` / `LOCAL_SEARCH_HOST`
environment variables if `18888` is taken.

```bash
node st-plugin/selfcheck.mjs   # start -> real search -> stop -> port released
```

### Running it by hand, without a window

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

### Chat Completion connects, then every reply fails

Symptom: the model list loads, Text Completion works, and Chat Completion
returns nothing. LM Studio's log has:

```
Engine protocol predict request returned 500:
While executing CallExpression at line 85, column 32 in source:
...{{- raise_exception('System message must be at the beginning...
Error: Jinja Exception: System message must be at the beginning.
```

That is the *model's chat template* refusing the prompt, not a connection
problem. Qwen3-family templates allow `system` only as the first message.
SillyTavern sends `system` messages mid-conversation all the time — the
jailbreak block, author's note, world info at depth, and the Web Search
extension's own injection, which lands at depth 2 as a system message.

Fix it with **Prompt Post-Processing** in the Chat Completion panel, under the
connection fields. `mergeMessages` in `src/prompt-converters.js` does exactly
what the template wants:

```js
// Force mid-prompt system messages to be user messages
if (i > 0 && mergedMessages[i].role === 'system') {
    mergedMessages[i].role = 'user';
}
```

| Option | `custom_prompt_post_processing` | Note |
|---|---|---|
| None | `''` | the broken default here |
| Semi-strict, tools | `semi_tools` | **use this** |
| Strict, tools | `strict_tools` | also works; pads with a `Let's get started.` filler turn |
| Semi-strict / Strict | `semi` / `strict` | same merge, but silently disables tool calling |

The `_tools` variants matter: `isToolCallingSupported()` in
`public/scripts/tool-calling.js` only sends tool definitions when
post-processing is `none`, `merge_tools`, `semi_tools` or `strict_tools`.
Picking plain `semi` fixes the crash and quietly turns off function calling.

Measured against this setup, same five messages with a system message in the
middle, through SillyTavern's own `/api/backends/chat-completions/generate`:

| Post-processing | Result |
|---|---|
| `''` | `{"error":{"message":"Bad Request"}}` |
| `semi_tools` | `'The current Rust version is 1.90.'` |

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
