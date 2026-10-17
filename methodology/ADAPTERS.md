# Adapters: tool-call fixes served beside a model

Some model and engine pairs fail an agent loop for a reason that is neither the model's skill nor the bench: the engine hands the
client tool arguments in a shape the client cannot use. This page publishes the small adapters the lab wrote for such cases, with
their tests and what they changed in a measured loop. An adapter never rewrites a model's text; it only reshapes tool arguments.

## qwen3_typed_array (vLLM 0.29.0, Qwen3-Coder)

**Problem.** Qwen3-Coder 30B-A3B often writes an array parameter as a Python list literal inside a string, for example
`"['pwd', 'ls -la /work']"`. vLLM's `qwen3_coder` tool parser passes that string through, so a client whose tool schema asks for an
array (Cline's `run_commands`) receives a string, and its shell runs the literal text: exit 127. On the night of 16 to 17 October
the AWQ INT4 build scored 1/6 on code-loop/v1 with the stock parser; its tool arguments arrived as stringified lists (an earlier
loop, the night before, gave two task verdicts and no complete score).

**Fix.** A tool-parser plugin that subclasses the stock parser (132 lines in v1, 146 in v2). Non-streaming responses are
normalised once. In streaming, the arguments of each tool call are buffered per call index and emitted once the call is complete
(a later call starts, or the stream ends through the parser's `finish_streaming` hook, which vLLM 0.29 calls at the end of every
engine-based stream); names, ids and content pass through unchanged. Only a string value of a property whose schema type is
`array`, starting with `[`, that `ast.literal_eval` (no code execution) turns into a list of strings (v1) or of JSON values (v2) is
converted; anything else is left exactly as produced and logged.

**Use.** `--enable-auto-tool-choice --tool-parser-plugin /plugins/qwen3_typed_array.py --tool-call-parser qwen3_typed_array`.

**Tests.** A CPU fixture streams synthetic Qwen3-Coder tool-call text token by token through the real parent parser and the
plugin, inside the `vllm/vllm-openai:v0.29.0` image with the model's tokenizer only (no GPU, no network): one and two commands, an
already valid JSON array, two calls in one answer, a string parameter that looks like a list (untouched), a non-literal
expression (untouched, never evaluated) and a mixed list. v1: 12/12 cases pass; v2 adds a list of objects: 14/14.

**Measured.** Same build, same frozen six tasks, thinking off, one loop per row. The stock row ran on an earlier launch line
(server context 16,384, Cline window 16,384, 8 sequences, memory 0.92). The plugin rows ran at server context 60,416 (Cline window
59,392, 4 sequences, memory 0.95), the largest one-card fit of the context probe. The context changed together with the parser:

| Parser | Server context | code-loop/v1 |
|---|---|---|
| stock `qwen3_coder` (night of 16 to 17 October) | 16,384 | 1/6 |
| `qwen3_typed_array` v1 (night of 17 to 18 October) | 60,416 | 3/6 |
| `qwen3_typed_array` v2 (night of 17 to 18 October) | 60,416 | 4/6 |
| `qwen3_typed_array` v2, repeated (night of 17 to 18 October) | 60,416 | 5/6 |

Plugin logs: one line per tool call whose array-typed parameter arrived as a string starting with `[`, and per call whose arguments
were not JSON.

| Outcome | v1 | v2 | v2, repeated |
|---|---|---|---|
| `run_commands` · `commands`: stringified list converted to an array | 75 | 68 | 64 |
| `read_files` · `files`: stringified list converted to an array | 0 | 26 | 21 |
| `search_codebase` · `queries`: stringified list converted to an array | 0 | 2 | 0 |
| `run_commands` · `commands`: not a literal, left unchanged | 7 | 26 | 7 |
| `read_files` · `files`: list of non-strings, left unchanged | 21 | 0 | 0 |
| `run_commands`: arguments not JSON, left unchanged | 1 | 0 | 0 |

v1 is n = 1 and v2 is n = 2. The plugin converted 75 of 104 logged calls in the v1 loop; 96 of 122 logged calls in the v2 loop; 85 of 92 logged calls in the v2, repeated loop.
The others reached the client unchanged, as strings where its schema asks for an array: in v1 mostly `read_files` lists of
objects (v2 converts them), in v2 `run_commands` values that start with `[` but are not Python literals. The integration defect is
reduced, not removed, and these loops are not a general coding grade.

### Source (v1)

```python
"""qwen3_typed_array: vLLM 0.29.0 tool parser for Qwen3-Coder whose array parameters reach the client as JSON arrays.

Qwen3-Coder sometimes writes an array parameter as a Python list literal inside a string ("['pwd', 'ls -la /work']").
The parent parser (qwen3_coder, engine based) then hands the client a string where the tool schema asks for an array,
and the agent's shell receives the literal text (exit 127). This parser keeps every byte of the parent's output except
the arguments of each tool call: they are buffered per call index, normalised once the call is complete (a later call
starts, or the stream finishes through finish_streaming), and emitted in one fragment. Only a string value of a property
whose schema type is "array", that starts with "[" and evaluates (ast.literal_eval, no code) to a list of strings, is
converted. Anything else is left exactly as produced and logged. Non-streaming responses get the same normalisation.
"""
from __future__ import annotations

import ast
import json
import logging

from vllm.entrypoints.generate.base.protocol import DeltaFunctionCall, DeltaMessage, DeltaToolCall
from vllm.tool_parsers.abstract_tool_parser import ToolParserManager
from vllm.tool_parsers.qwen3_engine_tool_parser import Qwen3EngineToolParser

MARKER = "RUN4_TYPED_ARRAY_PLUGIN_LOADED qwen3_typed_array"
log = logging.getLogger("vllm.qwen3_typed_array")
print(MARKER, flush=True)


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def tool_schema(request, name: str | None) -> dict:
    for tool in _get(request, "tools") or []:
        fn = _get(tool, "function")
        if fn is not None and _get(fn, "name") == name:
            return _get(fn, "parameters") or {}
    return {}


def normalise(arguments: str, schema: dict) -> tuple[str, list[str]]:
    """(arguments, notes): the arguments JSON with stringified string lists turned into arrays where the schema asks."""
    try:
        args = json.loads(arguments)
    except (TypeError, ValueError):
        return arguments, ["arguments are not JSON; left unchanged"]
    if not isinstance(args, dict):
        return arguments, []
    props = (schema or {}).get("properties") or {}
    notes, changed = [], False
    for key, value in list(args.items()):
        spec = props.get(key) or {}
        if spec.get("type") != "array" or not isinstance(value, str) or not value.lstrip().startswith("["):
            continue
        try:
            literal = ast.literal_eval(value.strip())
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            notes.append(f"{key}: not a literal; left unchanged")
            continue
        if isinstance(literal, list) and all(isinstance(x, str) for x in literal):
            args[key] = literal
            changed = True
            notes.append(f"{key}: stringified list of {len(literal)} string(s) converted")
        else:
            notes.append(f"{key}: literal is not a list of strings; left unchanged")
    return (json.dumps(args, ensure_ascii=False) if changed else arguments), notes


@ToolParserManager.register_module("qwen3_typed_array")
class Qwen3TypedArrayToolParser(Qwen3EngineToolParser):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._args: dict[int, str] = {}
        self._names: dict[int, str] = {}
        self._request = None

    def extract_tool_calls(self, model_output, request):
        info = super().extract_tool_calls(model_output, request)
        for tc in info.tool_calls or []:
            fixed, notes = normalise(tc.function.arguments, tool_schema(request, tc.function.name))
            if notes:
                log.warning("qwen3_typed_array %s: %s", tc.function.name, "; ".join(notes))
            tc.function.arguments = fixed
        return info

    def _flush(self, index: int) -> DeltaToolCall | None:
        raw = self._args.pop(index, None)
        if raw is None:
            return None
        fixed, notes = normalise(raw, tool_schema(self._request, self._names.get(index)))
        if notes:
            log.warning("qwen3_typed_array %s: %s", self._names.get(index), "; ".join(notes))
        return DeltaToolCall(index=index, function=DeltaFunctionCall(arguments=fixed))

    def _filter(self, delta: DeltaMessage | None) -> DeltaMessage | None:
        if delta is None or not delta.tool_calls:
            return delta
        out: list[DeltaToolCall] = []
        for tc in delta.tool_calls:
            for earlier in sorted(i for i in self._args if i < tc.index):  # a later call starts: earlier ones are complete
                flushed = self._flush(earlier)
                if flushed is not None:
                    out.append(flushed)
            fn = tc.function
            if fn is not None and fn.name:
                self._names[tc.index] = fn.name
            if fn is not None and fn.arguments:
                self._args[tc.index] = self._args.get(tc.index, "") + fn.arguments
                if tc.id or fn.name:  # keep the call's header, without its argument bytes
                    out.append(DeltaToolCall(index=tc.index, id=tc.id, type=tc.type,
                                             function=DeltaFunctionCall(name=fn.name)))
                continue
            out.append(tc)
        delta.tool_calls = out
        if not out and not delta.content and not getattr(delta, "reasoning", None):
            return None
        return delta

    def extract_tool_calls_streaming(self, previous_text, current_text, delta_text, previous_token_ids,
                                     current_token_ids, delta_token_ids, request):
        self._request = request
        return self._filter(super().extract_tool_calls_streaming(
            previous_text, current_text, delta_text, previous_token_ids, current_token_ids, delta_token_ids, request))

    def finish_streaming(self):
        delta = self._filter(super().finish_streaming())
        tail = [d for d in (self._flush(i) for i in sorted(self._args)) if d is not None]
        if tail:
            if delta is None:
                delta = DeltaMessage(tool_calls=tail)
            else:
                delta.tool_calls = (delta.tool_calls or []) + tail
        self._names.clear()
        return delta
```

### v2 changes

```diff
--- qwen3_typed_array.py (v1)
+++ qwen3_typed_array_v2.py (v2)
@@ -7,4 +7,4 @@
 starts, or the stream finishes through finish_streaming), and emitted in one fragment. Only a string value of a property
-whose schema type is "array", that starts with "[" and evaluates (ast.literal_eval, no code) to a list of strings, is
-converted. Anything else is left exactly as produced and logged. Non-streaming responses get the same normalisation.
+whose schema type is "array", that starts with "[" and evaluates (ast.literal_eval, no code) to a list of JSON values
+(v2; v1 accepted strings only), is converted. Anything else is left exactly as produced and logged. Non-streaming responses get the same normalisation.
 """
@@ -20,3 +20,3 @@
 
-MARKER = "RUN4_TYPED_ARRAY_PLUGIN_LOADED qwen3_typed_array"
+MARKER = "RUN4_TYPED_ARRAY_PLUGIN_LOADED qwen3_typed_array v2"
 log = logging.getLogger("vllm.qwen3_typed_array")
@@ -35,2 +35,15 @@
     return {}
+
+
+def _json_value(v, depth=0) -> bool:
+    """v2: a literal made only of JSON values (str, int, float, bool, None, lists and string-keyed dicts of them)."""
+    if depth > 20:
+        return False
+    if v is None or isinstance(v, (str, bool, int, float)):
+        return True
+    if isinstance(v, list):
+        return all(_json_value(x, depth + 1) for x in v)
+    if isinstance(v, dict):
+        return all(isinstance(k, str) and _json_value(x, depth + 1) for k, x in v.items())
+    return False
 
@@ -56,8 +69,9 @@
             continue
-        if isinstance(literal, list) and all(isinstance(x, str) for x in literal):
+        if isinstance(literal, list) and _json_value(literal):
             args[key] = literal
             changed = True
-            notes.append(f"{key}: stringified list of {len(literal)} string(s) converted")
+            kind = "string" if all(isinstance(x, str) for x in literal) else "JSON value"
+            notes.append(f"{key}: stringified list of {len(literal)} {kind}(s) converted")
         else:
-            notes.append(f"{key}: literal is not a list of strings; left unchanged")
+            notes.append(f"{key}: literal is not a list of JSON values; left unchanged")
     return (json.dumps(args, ensure_ascii=False) if changed else arguments), notes
```
