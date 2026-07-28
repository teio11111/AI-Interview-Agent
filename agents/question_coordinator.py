"""选题官 Agent - 审核、去重、整合三位出题官的题目"""
from agents.base_agent import BaseAgent
from utils.text_truncate import truncate_for_prompt


class QuestionCoordinatorAgent(BaseAgent):
    """选题官
    
    职责：接收三位出题官（项目深挖、技能验证、短板探测）的题目，
    进行去重、质量审核、难度分布调整，输出最终定稿。
    保留辩论机制：发现问题可要求某位出题官修订。
    """
    AGENT_NAME = "选题官"
    SYSTEM_PROMPT = """你是「选题官」，面试题目质量总负责人。

你的核心职责：
- 接收三位出题官的题目，进行统一审核
- 去重：相似考察点的题目只保留最好的
- 质量审核：每道题是否引用简历、是否有追问方向、难度是否合理、**是否包含 answer_directions（2-4 个回答方向关键词）**
- 难度分布调整：确保 easy/medium/hard 配比合理
- 最终排序：按考察顺序排列（项目深挖 → 技能验证 → 短板探测 → 场景设计）

工作原则：
- 总题数控制在 6-8 道
- 每类题目数量：项目深挖(3) + 技能验证(2) + 短板探测(1-2) + 场景设计(1)
- 如果某位出题官的题目质量不达标（包括缺少 answer_directions），标注问题并修订
- 最终题目必须都引用了简历原文
- 输出格式必须兼容现有面试系统
- **最终输出必须保留每道题的 answer_directions 字段**

请始终以严格的 JSON 格式输出，不要输出任何解释性文字。"""

    def select(self, project_questions, skill_questions, weakness_questions,
               position_name, resume_text, resume_analysis):
        """审核并整合三位出题官的题目（v2.1 纯代码版）

        Args:
            project_questions: 项目深挖出题官的结果
            skill_questions: 技能验证出题官的结果
            weakness_questions: 短板探测出题官的结果
            position_name: 岗位名称
            resume_text: 候选人简历原文
            resume_analysis: 简历评估结果

        Returns:
            dict: 最终定稿的题目列表
        """
        # 【v2.1 性能修复】如果三个出题官都成功，直接纯代码合并，不调 LLM。
        # 选 LLM 调用上耗时 30-40s 但仅做去重和难度调优，纯代码可代替。
        proj_qs = (project_questions or {}).get('questions') or []
        skill_qs = (skill_questions or {}).get('questions') or []
        weak_qs = (weakness_questions or {}).get('questions') or []

        if proj_qs and skill_qs and weak_qs:
            # 三个出题官都成功 → 纯代码合并 + 去重
            return self._merge_questions(proj_qs, skill_qs, weak_qs)

        # 有出题官失败 → 调用 LLM 备份
        import json

        resume_sum = truncate_for_prompt(self.summarize(resume_analysis), max_chars=2000)
        project_qs = truncate_for_prompt(json.dumps((project_questions or {}).get('questions', []), ensure_ascii=False, indent=2), max_chars=3500)
        skill_qs = truncate_for_prompt(json.dumps((skill_questions or {}).get('questions', []), ensure_ascii=False, indent=2), max_chars=3000)
        weakness_qs = truncate_for_prompt(json.dumps((weakness_questions or {}).get('questions', []), ensure_ascii=False, indent=2), max_chars=3500)

        prompt = f"""## 任务
你是选题官。三位出题官已分别提交了题目，请审核、去重、整合，输出最终定稿。

## 岗位名称
{position_name}

## 候选人简历
{resume_text or '暂无'}

## 简历评估结果（摘要，供参考）
{resume_sum}

## 项目深挖出题官的题目（应有3道）
{project_qs}

## 技能验证出题官的题目（应有2道）
{skill_qs}

## 短板探测出题官的题目（应有2-3道）
{weakness_qs}

## 审核标准

### 1. 去重检查
- 考察点相似的题目只保留最好的那道
- 标注被去掉的题目及原因

### 2. 质量检查（每道题）
- 是否引用了简历原文（resume_reference 不为空）
- follow_up_hints 是否具体可追问（非笼统描述）
- difficulty 是否与题目实际难度匹配
- intent 是否清晰明确

### 3. 难度分布
- easy: 1-2道（热身，建立候选人信心）
- medium: 3-4道（核心考察）
- hard: 1-2道（探测上限）

### 4. 回答方向关键词（answer_directions）检查（必查）
- 每道题必须包含 answer_directions 字段（2-4 个回答关键词/方向）
- 若缺失，请在最终输出中补上（基于题目内容推断）

### 5. 最终排序
项目深挖 → 技能验证 → 短板探测 → 场景设计

## 输出格式（严格 JSON，6-8道题）
{{
    "questions": [
        {{
            "question": "题目（可直接使用或微调）",
            "category": "项目深挖/技能验证/短板探测/场景设计",
            "difficulty": "easy/medium/hard",
            "resume_reference": "简历原文引用",
            "intent": "考察意图",
            "expected_depth": "合格回答标准",
            "follow_up_hints": ["追问方向1", "追问方向2"],
            "source": "来源出题官",
            "modified": false,
            "answer_directions": ["回答关键词/方向1", "回答关键词/方向2", "回答关键词/方向3", "回答关键词/方向4"]
        }}
    ],
    "review_log": {{
        "total_received": 8,
        "total_selected": 7,
        "removed": [
            {{"question_index": 1, "source": "来源", "reason": "去掉原因"}}
        ],
        "difficulty_distribution": {{"easy": 2, "medium": 3, "hard": 2}},
        "quality_notes": "整体质量评价",
        "missing_directions": "记录缺失 answer_directions 的题号，提示出题官补充"
    }},
    "approved": true
}}"""
        return self.think_json(prompt)

    def _merge_questions(self, project_qs, skill_qs, weakness_qs):
        """【v2.1 纯代码】合并三位出题官的题目（去重 + 来源标注 + 难度统计）

        替代选题官的 LLM 调用。三个出题官都成功时 → 不调 LLM，仅保留：
          - 去重：基于 question 文本关键词集合的 Jaccard 相似度（>0.6 视为重复）
          - 分类来源标注
          - answer_directions 字段透传
          - 难度分布统计

        Returns:
            dict: {questions, review_log, approved}
        """
        # 1. 收集所有题目 + 来源标签
        all_qs = []
        for q in (project_qs or []):
            q = dict(q)
            q['source'] = '项目深挖出题官'
            q['modified'] = False
            all_qs.append(q)
        for q in (skill_qs or []):
            q = dict(q)
            q['source'] = '技能验证出题官'
            q['modified'] = False
            all_qs.append(q)
        for q in (weakness_qs or []):
            q = dict(q)
            q['source'] = '短板探测出题官'
            q['modified'] = False
            all_qs.append(q)

        # 2. 去重：按 question 文本的关键词集合相似度
        import re

        def _keywords(text, top=12):
            text = re.sub(r'[^\w\u4e00-\u9fa5]', ' ', text or '')
            words = [w for w in text.split() if len(w) >= 2]
            return set(words[:top])

        unique = []
        removed = []
        for q in all_qs:
            qk = _keywords(q.get('question', ''))
            is_dup = False
            for u in unique:
                uk = _keywords(u.get('question', ''))
                if not qk or not uk:
                    continue
                jacc = len(qk & uk) / len(qk | uk)
                if jacc > 0.6:
                    is_dup = True
                    removed.append({
                        'question_index': len(unique),
                        'source': q.get('source'),
                        'reason': f'与已有题目相似 (Jaccard={jacc:.2f})',
                    })
                    break
            if not is_dup:
                unique.append(q)

        # 3. 难度分布统计
        diff_count = {'easy': 0, 'medium': 0, 'hard': 0}
        for q in unique:
            d = (q.get('difficulty') or 'medium').lower()
            if d not in diff_count:
                d = 'medium'
            diff_count[d] += 1

        return {
            'questions': unique,
            'review_log': {
                'total_received': len(all_qs),
                'total_selected': len(unique),
                'removed': removed,
                'difficulty_distribution': diff_count,
                'quality_notes': 'v2.1 纯代码合并（去重 + 来源标注 + 难度统计），未调 LLM',
                'missing_directions': '',
            },
            'approved': True,
        }

    def request_revision(self, original_questions, issues, resume_text):
        """要求出题官修订有问题的题目

        Args:
            original_questions: 原始题目列表
            issues: 审核发现的问题
            resume_text: 候选人简历原文

        Returns:
            dict: 修订后的题目
        """
        import json

        prompt = f"""## 任务
选题官审核发现以下题目存在问题，请根据反馈修订。

## 原始题目
{json.dumps(original_questions, ensure_ascii=False, indent=2)}

## 审核反馈
{json.dumps(issues, ensure_ascii=False, indent=2)}

## 候选人简历（供参考）
{resume_text or '暂无'}

## 修订原则
1. 只修改审核反馈中指出的问题
2. 修订后的题目仍需引用简历原文
3. 保持原有的 JSON 格式

## 输出格式（完整 JSON，包含所有题目）
{{
    "questions": [
        {{
            "question": "修订后的问题",
            "category": "项目深挖/技能验证/短板探测/场景设计",
            "difficulty": "easy/medium/hard",
            "resume_reference": "简历原文引用",
            "intent": "考察意图",
            "expected_depth": "合格回答标准",
            "follow_up_hints": ["追问方向1", "追问方向2"]
        }}
    ],
    "revision_notes": "修订说明"
}}"""
        return self.think_json(prompt)
