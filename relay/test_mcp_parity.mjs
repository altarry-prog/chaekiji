// 파이썬 판과 대조할 원격 상담 비서의 답을 뽑는다 — relay/test_mcp_parity.py가 부른다(혼자 돌려도 됨).
// 실행: node relay/test_mcp_parity.mjs <시나리오.json> <매일갱신자료.json>   → 표준출력에 사례별 답(JSON 배열)
import worker from "./worker.js";
import { mockFetch, call } from "./test_naru_mock.mjs";
import { readFileSync } from "node:fs";

const [scPath, snapPath] = process.argv.slice(2);
const sc = JSON.parse(readFileSync(scPath, "utf-8"));
const snapshot = JSON.parse(readFileSync(snapPath, "utf-8"));
globalThis.fetch = mockFetch(sc, snapshot);
const env = { NARU_KEY: "FAKE", NARU_WAIT_MS: "200" };
const out = [];
let id = 1;
for (const c of sc.cases) {
  const r = await call(worker, env, c.tool, c.args, id++);
  out.push({ tool: c.tool, args: c.args, isError: r.isError, result: r.isError ? r.text : r.out });
}
process.stdout.write(JSON.stringify(out));
