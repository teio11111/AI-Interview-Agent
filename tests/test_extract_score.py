"""_extract_score 鲁棒性单元测试（无需 LLM/Flask，1 秒跑完）

覆盖 5 种 LLM 真实返回结构：
  1) {score: 7, ...}                      顶层有 score
  2) {feedback: {score: 7, ...}, ...}     嵌套 feedback 子字段
  3) {score: '', score_breakdown: {...}}  score 空，从 breakdown 平均
  4) {score_tech: 7, score_soft: 6}       只有顾问分，按 6:4 加权
  5) {answer_quality: '一般'}             字符串兜底映射
  6) 全空 / None / 非字典                  兜底返回 5
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from routes.mobile_routes import _extract_score  # noqa: E402

CASES = [
    # (name, feedback_dict, expected_score)
    ("1. 顶层 score=7", {"score": 7, "evaluation": "ok"}, 7),
    ("1. 顶层 score='8' 字符串", {"score": "8", "evaluation": "ok"}, 8),
    ("1. 顶层 score=0 应被忽略，回退到 breakdown", {
        "score": 0, "score_breakdown": {"accuracy": 6, "depth": 7, "practicality": 8}
    }, 7),  # (6+7+8)/3 = 7
    ("2. 嵌套 feedback.score=9", {
        "evaluation": "ok", "feedback": {"score": 9, "answer_quality": "优秀"}
    }, 9),
    ("3. score='' + score_breakdown 5维平均", {
        "score": "",
        "score_breakdown": {
            "accuracy": 6, "depth": 8, "practicality": 7, "logic": 5, "completeness": 9
        }
    }, 7),  # (6+8+7+5+9)/5 = 7
    ("3. score=None + breakdown 含非数值", {
        "score": None,
        "score_breakdown": {"accuracy": 6, "depth": "bad", "practicality": 8}
    }, 7),  # 只取数值 (6+8)/2 = 7
    ("4. score_tech=8 score_soft=6 加权", {
        "score_tech": 8, "score_soft": 6
    }, 7),  # 8*0.6 + 6*0.4 = 7.2 -> round=7
    ("4. score_tech=10 score_soft=5 加权", {
        "score_tech": 10, "score_soft": 5
    }, 8),  # 10*0.6 + 5*0.4 = 8
    ("5. answer_quality='优秀'", {"answer_quality": "优秀"}, 8),
    ("5. answer_quality='一般'", {"answer_quality": "一般"}, 5),
    ("5. answer_quality='较差'", {"answer_quality": "较差"}, 3),
    ("混合: 顶层 score + breakdown 都存在（优先顶层）", {
        "score": 6,
        "score_breakdown": {"accuracy": 10, "depth": 10, "practicality": 10}
    }, 6),
    ("混合: score='' + 嵌套 feedback.score", {
        "score": "",
        "feedback": {"score": 8}
    }, 8),
    ("兜底: 完全空 dict", {}, 5),
    ("兜底: None", None, 5),
    ("兜底: 非字典", "garbage", 5),
    ("边界: score=15 裁剪到 10", {"score": 15}, 10),
    ("边界: score=-5 裁剪到 1", {"score": -5}, 1),
    ("边界: score='abc' 解析失败", {"score": "abc", "answer_quality": "良好"}, 7),
]


def main() -> int:
    print("=" * 70)
    print(f"  _extract_score 单元测试 — {len(CASES)} 个用例")
    print("=" * 70)
    passed = 0
    failed = 0
    for name, feedback, expected in CASES:
        actual = _extract_score(feedback)
        ok = actual == expected
        marker = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  [{marker}] {name:<55s} expected={expected}  actual={actual}")
    print("=" * 70)
    print(f"  结果: passed={passed}  failed={failed}")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())