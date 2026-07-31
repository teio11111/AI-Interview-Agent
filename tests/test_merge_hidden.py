"""【v4.1 演示前】_merge_hidden_results 合并逻辑单元测试

覆盖 v4.1 新加的 hidden 评估师拆分合并函数的 5 个关键场景。
不需要 pytest，纯 unittest + Python 标准库。

运行方式：
    cd c:\\Users\\Teio\\Desktop\\AI-Interview-Agent
    python -m unittest tests.test_merge_hidden -v
"""
import sys
import os
import unittest

# 允许独立运行（无需 app context）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.agent_orchestrator import AgentOrchestrator


def _call_merge(sub_a, sub_b):
    """直接调用 _merge_hidden_results（不依赖 self）"""
    return AgentOrchestrator._merge_hidden_results(None, sub_a, sub_b)


class TestMergeHiddenResults(unittest.TestCase):
    """v4.1 hidden 评估拆分合并逻辑测试"""

    # ==================== Case 1: 正常合并 ====================
    def test_normal_merge_sub_a_and_sub_b(self):
        """sub_a + sub_b 都有 → 9 维度齐全，hidden_score 正确计算"""
        sub_a = {
            'candidate_profile': {
                'education': {'school_tier': '211', 'score': 7, 'detail': '华东理工'},
                'residence': {'current_city': '上海', 'score': 9, 'detail': '本地'},
                'career_direction': {'preferred_track': '技术专家', 'score': 8, 'detail': '方向一致'},
            },
            'implicit_requirement_mapping': [
                {'dimension': '抗压', 'match_status': '匹配', 'detail': '高强度项目经历'},
            ],
        }
        sub_b = {
            'candidate_profile': {
                'job_stability': {'level': '稳定', 'score': 7},
                'emotional_stability': {'level': '较好', 'score': 6},
                'communication_ability': {'level': '较强', 'score': 7},
                'teamwork_style': {'style': '协作型', 'score': 6},
                'learning_ability': {'level': '强', 'score': 8},
                'resume_authenticity': {'level': '真实', 'score': 9},
            },
            'hidden_score_breakdown': {
                'job_stability': 7,
                'emotional_stability': 6,
                'communication_ability': 7,
                'teamwork_style': 6,
                'learning_ability': 8,
                'resume_authenticity': 9,
            },
            'hidden_risks': [{'risk': '暂无明显风险', 'severity': '低'}],
            'hidden_highlights': [{'highlight': '技术栈丰富'}],
            'hidden_summary': '候选人整体隐性维度表现良好',
        }

        result = _call_merge(sub_a, sub_b)

        # 1. candidate_profile 应包含 9 个维度
        self.assertEqual(len(result['candidate_profile']), 9)
        self.assertIn('education', result['candidate_profile'])
        self.assertIn('resume_authenticity', result['candidate_profile'])

        # 2. implicit_requirement_mapping 透传 sub_a
        self.assertEqual(len(result['implicit_requirement_mapping']), 1)

        # 3. hidden_score_breakdown 9 维度齐全
        self.assertEqual(len(result['hidden_score_breakdown']), 9)

        # 4. risks / highlights / summary 透传 sub_b
        self.assertEqual(len(result['hidden_risks']), 1)
        self.assertEqual(len(result['hidden_highlights']), 1)
        self.assertIn('良好', result['hidden_summary'])

        # 5. hidden_score 正确计算：sub_a 平均 8 + sub_b 平均 7.17 ≈ 75.6
        #    实际：education=7, residence=9, career_direction=8 (sub_a)
        #          job_stability=7, emotional_stability=6, communication_ability=7,
        #          teamwork_style=6, learning_ability=8, resume_authenticity=9 (sub_b)
        #    平均 = (7+9+8+7+6+7+6+8+9)/9 = 67/9 ≈ 7.44 → 74
        self.assertEqual(result['hidden_score'], 74)
        self.assertEqual(result['hidden_score_source'], 'system:9_dim_avg_v4.1_split')

    # ==================== Case 2: sub_a 失败（None） ====================
    def test_sub_a_failed_only_sub_b(self):
        """sub_a 返回 None，sub_b 完整 → 用 sub_b 全部维度，sub_a 维度补 5"""
        sub_a = None
        sub_b = {
            'candidate_profile': {
                'job_stability': {'score': 8},
                'emotional_stability': {'score': 7},
                'communication_ability': {'score': 8},
                'teamwork_style': {'score': 7},
                'learning_ability': {'score': 8},
                'resume_authenticity': {'score': 9},
            },
            'hidden_score_breakdown': {
                'job_stability': 8,
                'emotional_stability': 7,
                'communication_ability': 8,
                'teamwork_style': 7,
                'learning_ability': 8,
                'resume_authenticity': 9,
            },
            'hidden_summary': 'sub_a 失败，仅 sub_b 结果',
        }

        result = _call_merge(sub_a, sub_b)

        # 应不崩，且有结果
        self.assertIsNotNone(result)
        # 9 维度齐全
        self.assertEqual(len(result['hidden_score_breakdown']), 9)
        # sub_a 维度默认 5
        self.assertEqual(result['hidden_score_breakdown']['education'], 5)
        self.assertEqual(result['hidden_score_breakdown']['residence'], 5)
        self.assertEqual(result['hidden_score_breakdown']['career_direction'], 5)
        # summary 透传
        self.assertIn('sub_a 失败', result['hidden_summary'])

    # ==================== Case 3: sub_b 失败 ====================
    def test_sub_b_failed_only_sub_a(self):
        """sub_b 失败，sub_a 完整 → 用 sub_a 维度，sub_b 维度补 5"""
        sub_a = {
            'candidate_profile': {
                'education': {'score': 8},
                'residence': {'score': 7},
                'career_direction': {'score': 9},
            },
            'implicit_requirement_mapping': [
                {'dimension': '稳定性期望', 'match_status': '匹配'},
            ],
        }
        sub_b = None

        result = _call_merge(sub_a, sub_b)

        # 应不崩
        self.assertIsNotNone(result)
        # 9 维度齐全（sub_b 维度补 5）
        self.assertEqual(len(result['hidden_score_breakdown']), 9)
        self.assertEqual(result['hidden_score_breakdown']['job_stability'], 5)
        # sub_a 维度使用真实分数
        self.assertEqual(result['hidden_score_breakdown']['education'], 8)
        # implicit_requirement_mapping 透传
        self.assertEqual(len(result['implicit_requirement_mapping']), 1)

    # ==================== Case 4: 都失败 ====================
    def test_both_failed_returns_none(self):
        """sub_a + sub_b 都失败 → 返回 None"""
        result = _call_merge(None, None)
        self.assertIsNone(result)

        # 也测试空 dict
        result2 = _call_merge({}, {})
        # 两个空 dict 视为"都失败"，应返回 None
        self.assertIsNone(result2)

    # ==================== Case 5: 边界 - sub_b 缺字段 ====================
    def test_sub_b_missing_optional_fields(self):
        """sub_b 缺 hidden_summary / risks / highlights → 不崩，缺字段为空"""
        sub_a = {
            'candidate_profile': {
                'education': {'score': 6},
                'residence': {'score': 7},
                'career_direction': {'score': 6},
            },
        }
        sub_b = {
            'candidate_profile': {
                'job_stability': {'score': 7},
                'emotional_stability': {'score': 6},
                'communication_ability': {'score': 7},
                'teamwork_style': {'score': 6},
                'learning_ability': {'score': 7},
                'resume_authenticity': {'score': 8},
            },
            'hidden_score_breakdown': {
                'job_stability': 7,
                'emotional_stability': 6,
                'communication_ability': 7,
                'teamwork_style': 6,
                'learning_ability': 7,
                'resume_authenticity': 8,
            },
            # 注意：故意不传 hidden_risks / hidden_highlights / hidden_summary
        }

        result = _call_merge(sub_a, sub_b)

        # 不应崩
        self.assertIsNotNone(result)
        # 缺字段：risks/highlights 缺失时 key 不存在，summary 缺失时 key 不存在
        self.assertNotIn('hidden_risks', result)
        self.assertNotIn('hidden_highlights', result)
        self.assertNotIn('hidden_summary', result)
        # 但核心字段（profile + breakdown）必须有
        self.assertEqual(len(result['candidate_profile']), 9)
        self.assertEqual(len(result['hidden_score_breakdown']), 9)
        # hidden_score 必须有
        self.assertIn('hidden_score', result)
        self.assertIsInstance(result['hidden_score'], int)

    # ==================== Bonus Case 6: LLM 严重偏低兜底 ====================
    def test_extreme_low_score_floor(self):
        """9 维度全 1 分（极端负面）→ 兑底升至 50 分"""
        sub_a = {
            'candidate_profile': {
                'education': {'score': 1},
                'residence': {'score': 1},
                'career_direction': {'score': 1},
            },
        }
        sub_b = {
            'candidate_profile': {
                'job_stability': {'score': 1},
                'emotional_stability': {'score': 1},
                'communication_ability': {'score': 1},
                'teamwork_style': {'score': 1},
                'learning_ability': {'score': 1},
                'resume_authenticity': {'score': 1},
            },
            'hidden_score_breakdown': {
                'job_stability': 1,
                'emotional_stability': 1,
                'communication_ability': 1,
                'teamwork_style': 1,
                'learning_ability': 1,
                'resume_authenticity': 1,
            },
        }

        result = _call_merge(sub_a, sub_b)

        # 平均 1.0/10 ≤ 2.5 → 兑底升至 5.0/10 → 50 分
        self.assertEqual(result['hidden_score'], 50)


if __name__ == '__main__':
    # 支持 python -m unittest 和 python tests/test_merge_hidden.py 两种方式
    unittest.main(verbosity=2)
