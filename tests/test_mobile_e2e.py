"""
mobile_routes 端到端联调测试。

覆盖：
  1. GET  /positions  - 岗位列表（鉴权 + 列表返回）
  2. POST /questions  - 拉题 + 自动建候选人/会话（耗时 30-60s）
  3. POST /chat       - 提交回答 → AI 追问反馈（多轮）
  4. POST /result     - 结束面试 → 板块切分 + 报告

用法：
  python _test_mobile_e2e.py
  python _test_mobile_e2e.py --quick         # 跳过慢步骤
  python _test_mobile_e2e.py --device-id dev001 --position-id 1
"""
import argparse
import json
import sys
import time

import requests

BASE = "http://127.0.0.1:8088/api/mobile"
DEFAULT_TOKEN = "mobile-demo-2026"


def auth_headers(token: str) -> dict:
    return {"X-Demo-Token": token, "Content-Type": "application/json"}


def banner(s: str) -> None:
    print("\n" + "=" * 60)
    print(f"  {s}")
    print("=" * 60)


def fmt_obj(o, max_len: int = 400) -> str:
    """格式化 JSON 对象。"""
    s = json.dumps(o, ensure_ascii=False, indent=2)
    if len(s) > max_len:
        s = s[:max_len] + f"\n... (+{len(s) - max_len} chars)"
    return s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--token", default=DEFAULT_TOKEN)
    ap.add_argument("--device-id", default=f"local-test-{int(time.time())}")
    ap.add_argument("--position-id", type=int, default=None,
                    help="不指定则自动选第一个有 AI 解析的岗位")
    ap.add_argument("--quick", action="store_true", help="跳过出题（用空 questions）")
    ap.add_argument("--chat-rounds", type=int, default=2)
    ap.add_argument("--skip-result", action="store_true")
    args = ap.parse_args()

    H = auth_headers(args.token)
    ok = 0
    fail = 0

    # ---------- 1. 岗位列表 ----------
    banner("1. GET /positions")
    r = requests.get(f"{args.base}/positions", headers=H, timeout=15)
    if r.status_code != 200 or r.json().get("code") != 200:
        print(f"FAIL: status={r.status_code}, body={r.text[:200]}")
        fail += 1
        return 1
    positions = r.json()["data"]["positions"]
    print(f"OK: 拿到 {len(positions)} 个岗位")
    for p in positions[:5]:
        print(f"  - [{p['id']:>3}] {p['name'][:30]}  ai={p['has_ai_analysis']}")
    ok += 1

    # 选岗位
    if args.position_id:
        pid = args.position_id
    else:
        candidates = [p for p in positions if p["has_ai_analysis"]]
        if not candidates:
            print("FAIL: 没有带 AI 解析的岗位可测")
            return 1
        pid = candidates[0]["id"]
    print(f"\n使用岗位 id={pid}")

    # ---------- 2. 拉题 ----------
    banner(f"2. POST /questions (position_id={pid}, device_id={args.device_id})")
    t0 = time.time()
    r = requests.post(
        f"{args.base}/questions",
        headers=H,
        json={"position_id": pid, "device_id": args.device_id,
              "candidate_name": f"测试-{args.device_id[-6:]}"},
        timeout=300,
    )
    elapsed = time.time() - t0
    print(f"耗时 {elapsed:.1f}s, status={r.status_code}")
    if r.status_code != 200 or r.json().get("code") != 200:
        print(f"FAIL: {r.text[:300]}")
        fail += 1
        return 1
    qdata = r.json()["data"]
    session_id = qdata["session_id"]
    candidate_id = qdata["candidate_id"]
    questions = qdata.get("questions", {})
    if isinstance(questions, dict):
        q_list = questions.get("questions", [])
    else:
        q_list = questions or []
    print(f"OK: session_id={session_id}, candidate_id={candidate_id}, 题目数={len(q_list)}")
    if q_list:
        for i, q in enumerate(q_list[:3]):
            qt = q.get("question") if isinstance(q, dict) else str(q)
            print(f"  - Q{i+1}: {str(qt)[:80]}")
    ok += 1

    if args.quick or not q_list:
        print("\n[quick 模式 / 无题目，跳过 chat + result]")
        return 0 if fail == 0 else 1

    # ---------- 3. 多轮对话 ----------
    banner(f"3. POST /chat ({args.chat_rounds} 轮)")
    for i in range(min(args.chat_rounds, len(q_list))):
        q_obj = q_list[i]
        q_text = q_obj.get("question") if isinstance(q_obj, dict) else str(q_obj)
        answer = f"这是我对【{q_text[:30]}】的测试回答：我在相关项目中有 3 年经验。"
        t0 = time.time()
        r = requests.post(
            f"{args.base}/chat",
            headers=H,
            json={"session_id": session_id, "question": q_text, "answer": answer},
            timeout=120,
        )
        elapsed = time.time() - t0
        print(f"\n--- 第 {i+1} 轮 ---")
        print(f"耗时 {elapsed:.1f}s, status={r.status_code}")
        if r.status_code != 200 or r.json().get("code") != 200:
            print(f"FAIL: {r.text[:300]}")
            fail += 1
            continue
        cdata = r.json()["data"]
        feedback = cdata.get("feedback", {})
        if isinstance(feedback, dict):
            feedback_str = json.dumps(feedback, ensure_ascii=False)
            top_score = cdata.get("score", feedback.get("score", ""))
        else:
            feedback_str = str(feedback)
            top_score = cdata.get("score", "")
        print(f"OK: 反馈={feedback_str[:160]}{'...' if len(feedback_str) > 160 else ''}")
        print(f"     score={top_score}, keys={list(cdata.keys())[:8]}")
        ok += 1

    # ---------- 4. 结束面试 ----------
    if args.skip_result:
        print("\n[--skip-result，跳过 result]")
        return 0 if fail == 0 else 1

    banner("4. POST /result")
    t0 = time.time()
    r = requests.post(
        f"{args.base}/result",
        headers=H,
        json={"session_id": session_id},
        timeout=300,
    )
    elapsed = time.time() - t0
    print(f"耗时 {elapsed:.1f}s, status={r.status_code}")
    if r.status_code != 200 or r.json().get("code") != 200:
        print(f"FAIL: {r.text[:300]}")
        fail += 1
    else:
        rdata = r.json()["data"]
        print(f"OK: session_status={rdata.get('session_status')}")
        report = rdata.get("report") or rdata.get("summary") or rdata
        if isinstance(report, dict):
            print(f"     报告 keys = {list(report.keys())[:8]}")
        ok += 1

    # ---------- 总结 ----------
    banner(f"总结: ok={ok}, fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
