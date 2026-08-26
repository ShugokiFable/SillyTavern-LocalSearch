# SillyTavern: local model + free web search

Web search in SillyTavern with **no API key and no account**, and a local
LM Studio model that actually answers instead of silently failing.

Everything runs on your own machine. Nothing leaves it except the search query.

---

## Install

**Close SillyTavern first.** While its browser tab is open it writes its own
copy of the settings back over the file, so anything changed underneath is lost.

1. Download this repo (green **Code** button → **Download ZIP**, then unzip) or:

   ```bash
   git clone https://github.com/ShugokiFable/SillyTavern-LocalSearch
   ```

2. Double-click **`Install.bat`**.

That is the whole install. It finds SillyTavern, installs the one dependency,
turns on server plugins, links the plugin in, and sets the two settings that
otherwise make this look broken. Re-running it is safe.

If it cannot find SillyTavern it asks once for the path. You can also pass it:

```bash
python install.py --sillytavern "C:\path\to\SillyTavern"
python install.py --dry-run
```

Start SillyTavern. Its console should say:

```
[local-search] started on http://127.0.0.1:18888
```

**To search the web, wrap the query in backticks** in any chat message:

> Hey, can you check `current version of rust` for me?

That is the only thing that triggers a search. See
[Web search fires on almost every roleplay turn](#web-search-fires-on-almost-every-roleplay-turn)
for why the alternative is worse.

### Using LM Studio as the model

Load a model in LM Studio and start its server (`lms server start`, or the
toggle in the app). Then in SillyTavern:

**API Connections** → API: **Chat Completion** → Source: **Custom
(OpenAI-compatible)**

| Field | Value |
|---|---|
| Custom Endpoint | `http://127.0.0.1:1234/v1` |
| Custom API Key | any non-empty text, e.g. `local` |
| Prompt Post-Processing | **Semi-strict, tools** |
| Response (tokens) | **1024 or more** |

Every one of those four has a failure mode that looks like something else
entirely. They are documented, with measurements, in
[section 2](#2-lm-studio-as-a-sillytavern-api).

### What the installer changes

| | |
|---|---|
| `pip install ddgs` | the one dependency, DuckDuckGo search |
| `config.yaml` | `enableServerPlugins: true` |
| `plugins/local-search` | junction to `st-plugin/`, so search starts and stops with SillyTavern |
| Web Search settings | source `searxng`, URL `http://127.0.0.1:18888`, backticks on, trigger phrases **off** |
| `custom_prompt_post_processing` | `semi_tools` — only if you are already on Custom (OpenAI-compatible) |

It backs up `settings.json` to `settings.json.bak-install` before its first
write, and never touches your presets, characters or chats.

---

## The rest of this file

is what was measured to get there, and is only worth reading when something
misbehaves:

- [1. Free web search](#1-free-web-search) — why none of the built-in sources are free, and what the shim implements
- [2. LM Studio as a SillyTavern API](#2-lm-studio-as-a-sillytavern-api) — four failures that look like connection problems
- [3. What this costs at run time](#3-what-this-costs-at-run-time) — the settings that quietly slow every turn
- [4. Vectors](#4-local-rag-on-the-same-endpoint-vectors) and [5. Connection Profiles](#5-one-click-per-backend-connection-profiles) — optional extras

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

### Setting it up by hand

`Install.bat` does all of this. If you would rather not run it:

```bash
python -m pip install ddgs
```

Run `Start-LocalSearch.bat` (or `python local_search.py`) and leave it open.
In SillyTavern, **Extensions → Web Search**:

- Source: **SearXNG**
- SearXNG URL: `http://127.0.0.1:18888`
- **Trigger Phrases: off**, **Backticks: on**

Then wrap a query in backticks to search.

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

### The preset silently puts the crash back

`custom_prompt_post_processing` lives in **two** places: `oai_settings` in
`settings.json`, and every Chat Completion **preset** file in
`data/<user>/OpenAI Settings/`. Loading a preset overwrites the live value.

So fixing the dropdown and then switching presets — or just reloading the one
you already had — restores `""` and the Jinja exception comes back, with no
obvious connection to what you changed. Fix it in the preset you actually use,
not only in the panel.

Presets carry `openai_max_context` too, which is the other half of the same
trap: a preset written for a hosted model can hold a context far larger than
anything you can load locally.

---

## 3. What this costs at run time

Three settings look free and are not. All three were measured on a 16 GB card
running a model whose weights are 16.24 GB, which is the interesting case.

### Web search fires on almost every roleplay turn

The extension ships **52 trigger phrases**, and they are not "search-shaped":

```
can you · tell me · what is · what are · who is · why do · why is
how to · how does · how do you · where is · when did · find me · explain me
```

Ordinary in-character dialogue hits those constantly. Every hit is a live
DuckDuckGo round trip plus an injected block at depth 2, on a turn where nobody
asked for the web.

Turn **trigger phrases off** and leave **backticks on**. Search then happens
when you write `` `current rust version` `` and at no other time, which is what
"search when I ask" actually means.

### Vectors needs VRAM you may not have

Embeddings are a *second model*. If the chat model already fills the card,
every embed call evicts it, and the next turn reloads 16 GB from disk:

```
00:27:27  POST /v1/embeddings                        <- Vectors, on a normal turn
00:27:28  ERROR ... Model is unloaded.               <- chat model evicted
00:27:29  [LlamaEmbeddingEngine] Model load complete!
00:27:33  POST /v1/chat/completions                  <- reloading 16 GB to answer
```

`lms ps` tells you before you start:

```
qwen3.6-35b-...   18.34 GB   65536      <- footprint
nvidia-smi        15454 MiB used, 592 MiB free of 16376 MiB
```

18.34 GB of model against 592 MiB of headroom. There is no room for an 84 MB
embedder, or for anything else. Vectors is worth having when the numbers leave
room for it and is actively harmful when they do not.

### Reasoning tokens are the latency, and the API cannot turn them off

A reasoning model spends the reply budget thinking first. Measured on this one,
asking for a single sentence:

| Request | completion tokens | of which reasoning | visible text |
|---|---|---|---|
| baseline | 362 | 331 | one sentence |
| `reasoning_effort: low` | 363 | 330 | one sentence |
| `/no_think` in the message | 778 | 747 | one sentence |
| `/nothink` in the message | 490 | 456 | one sentence |
| `chat_template_kwargs: {enable_thinking: false}` | — | — | `{"error":"terminated"}` |

None of the usual switches work. `reasoning_effort` is accepted and ignored,
the Qwen `/no_think` soft switches make it *think harder*, and
`chat_template_kwargs` is rejected outright. A real roleplay turn on this setup
decoded 3,318 tokens at 52 tok/s — about a minute of thinking before the first
visible word.

The only working control is on the server side: LM Studio's
`llm.prediction.reasoning.budgetTokens`, set in the model's config in the
Developer tab. It is not reachable through the OpenAI-compatible API, so no
SillyTavern setting can substitute for it.

### JIT loading picks its own context length

Letting SillyTavern's first request load the model is convenient and quietly
wrong. LM Studio sizes a just-in-time load to the request it is answering:

```
lms ps
qwen3.6-35b-...   IDLE   18.34 GB   5888        <- after a short first message
```

5,888 tokens. The first long roleplay prompt then does not fit and the model is
reloaded — 16 GB off disk, mid-conversation. Load it yourself instead, once:

```bash
lms load <model-key> -c 65536 --ttl 86400
```

`--ttl` is what stops it being unloaded again between sessions; the default is
an hour.

### The weights have to fit, and context length will not save you

`lms load --estimate-only` reports the same **17.08 GiB** at 65,536, 32,768 and
16,384 context, because the KV cache is not what is over budget — the weights
are:

```
Hermes3.6-35B-A3B-...-APEX-Compact.gguf    16.24 GB
RTX 4080 SUPER                             15.99 GB usable
```

Shrinking context does not make a 16.24 GB model fit a 15.99 GB card. Only a
smaller quantisation does. Generation still runs at ~52 tok/s because an
A3B mixture-of-experts activates about 3B parameters per token, so the spill
hurts prompt processing far more than it hurts streaming.

---

## 4. Local RAG on the same endpoint (Vectors)

If LM Studio also serves an embedding model, the **Vectors** extension gets you
retrieval over your chats and files with no second service and no key.

**Check `lms ps` against `nvidia-smi` first.** This is a second model competing
for the same card; see section 3 for what happens when it does not fit.

There is no "custom OpenAI-compatible" option in the Vectorization Source
dropdown, which makes it look unsupported. Use **vLLM** — [`src/vectors/vllm-vectors.js`](https://github.com/SillyTavern/SillyTavern/blob/release/src/vectors/vllm-vectors.js)
POSTs plain `{ input, model }` to `<url>/v1/embeddings`, which is exactly what
LM Studio serves:

| Field | Value |
|---|---|
| Vectorization Source | **vLLM** |
| Use alternative endpoint | **on** |
| Alt endpoint URL | `http://127.0.0.1:1234/v1` |
| Model | `text-embedding-nomic-embed-text-v1.5` |

The alt-endpoint toggle matters: without it the extension reads the vLLM server
URL out of the Text Completion settings instead, and `validateSettings()`
throws `Vectors: API URL missing` before any request goes out.

No API key is needed. `setAdditionalHeadersByType` sends no `Authorization`
header when the vLLM secret is unset, and LM Studio does not check one.

Measured through SillyTavern's own `/api/vector/insert` and `/api/vector/query`,
three unrelated sentences indexed, then queried with wording that shares no
words with any of them:

```
query: "what weapon does she hide"
  1. "Seraphina keeps a silver dagger under her pillow."
  2. "Rust 1.90 was current at the time of writing."
  3. "The tavern in Riverwood serves mead brewed with juniper."
```

768 dimensions, batches of 5, entirely on the same GPU already holding the chat
model.

---

## 5. One click per backend (Connection Profiles)

Switching between a local model and a hosted one means changing the source, the
URL, the model, the preset and the post-processing dropdown, in that order,
every time. **Connection Profiles** (in the API panel) collapse that into one
select.

A profile is stored in `extension_settings.connectionManager.profiles`:

```json
{
    "id": "<uuid>",
    "mode": "cc",
    "name": "LM Studio (local)",
    "api": "custom",
    "preset": "<your preset> (LM Studio)",
    "api-url": "http://127.0.0.1:1234/v1",
    "model": "qwen3.6-35b-a3b-uncensored-genesis-hermes-v10",
    "prompt-post-processing": "semi_tools",
    "exclude": []
}
```

`api` takes a key from `CONNECT_API_MAP` — `custom` for Custom
(OpenAI-compatible), `openrouter` for OpenRouter, and so on. Applying a profile
replays those fields as slash commands in a fixed order and skips any that are
empty, so a partial profile is fine.

Because the profile sets **both** the preset and the post-processing, it is also
the durable answer to the trap above: pick the profile and the pair can no
longer drift apart.

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
