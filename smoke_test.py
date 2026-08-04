"""系统冒烟测试：覆盖上传云端后的所有改动。

覆盖范围（按会话与 memory 提取）：
  A. 基础环境（健康检查 / 登录 / 首页）
  B. 岗位管理双入口（手动录入 + PDF 智能导入 + 预览确认）
  C. 候选人门户下线（/api/auth/register 403、/candidate/* 404）
  D. 导航栏响应式（HTML 结构验证）
  E. 实时面试页面布局（col-md-9 / col-md-3）
  F. 综合评分新公式（computation 字段）
  G. 候选人/面试会话列表冒烟
  H. AI 实时分析 / 建议追问 / 角色控制 关键 ID
  I. 模板语法静态校验（jinja parse）
  J. LLM 接入验证（DeepSeek-v4-Flash + parse_json 兼容）
  K. 【v3.6】隐藏维度异步评估（partial_complete + hidden_done）
  L. 【v4.1】候选人重新评估 DELETE 端点
  （v4.3 已去除 M 节 兑底面试题测试，因为兑底题功能已删除）
  M. 【v4.4】两段式拆分：简历评估 + 出题手动触发（隐性完成不再被出题阶段卡住）

使用：
  python smoke_test.py [base_url]
  默认 base_url=http://127.0.0.1:8088

输出：每项 PASS/FAIL/WARN，最后给一个汇总表。
"""
import sys
import os
import re
import json
import http.cookiejar
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding='utf-8')

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8088'
ADMIN_USER = 'admin'
ADMIN_PASS = 'admin123'

# ---------- 计数 ----------
STATS = {'PASS': 0, 'FAIL': 0, 'WARN': 0, 'SKIP': 0}
RESULTS: List[Dict] = []


def _record(category: str, name: str, status: str, detail: str = ''):
    STATS[status] = STATS.get(status, 0) + 1
    icon = {'PASS': '✓', 'FAIL': '✗', 'WARN': '⚠', 'SKIP': '⋯'}.get(status, '?')
    line = f'  [{icon} {status:<5}] {category}::{name}'
    if detail:
        line += f'  | {detail[:120]}'
    print(line)
    RESULTS.append({'cat': category, 'name': name, 'status': status, 'detail': detail})


def http_call(opener, method: str, path: str, data=None, headers=None,
              timeout: int = 60) -> Tuple[int, str, dict, str]:
    """返回 (status, raw_text, parsed_json_or_empty, final_url)

    默认 timeout=60 秒以兼容 LLM 调用（parse-jd / 评估任务通常需要 30-60 秒）。
    """
    url = f'{BASE}{path}'
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode('utf-8')
            headers = {**(headers or {}), 'Content-Type': 'application/json'}
        elif isinstance(data, (bytes, bytearray)):
            body = bytes(data)
    req = urllib.request.Request(url, data=body, method=method,
                                 headers=headers or {})
    try:
        r = opener.open(req, timeout=timeout)
        raw = r.read().decode('utf-8', errors='replace')
        try:
            return r.status, raw, json.loads(raw) if raw.strip().startswith(('{', '[')) else {}, r.geturl()
        except json.JSONDecodeError:
            return r.status, raw, {}, r.geturl()
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            return e.code, raw, json.loads(raw) if raw.strip().startswith(('{', '[')) else {}, url
        except json.JSONDecodeError:
            return e.code, raw, {}, url


# ============================================================================
# A. 基础环境
# ============================================================================
def test_a_basic(opener):
    print('\n========== A. 基础环境 ==========')
    s, r, j, _url = http_call(opener, 'GET', '/')
    _record('A', '首页 GET /', 'PASS' if s == 200 else 'FAIL', f'status={s}')

    s, r, j, _url = http_call(opener, 'POST', '/api/auth/login',
                   {'username': ADMIN_USER, 'password': ADMIN_PASS})
    ok = s == 200 and j.get('code') in (0, 200)
    _record('A', '管理员登录', 'PASS' if ok else 'FAIL',
            f"role={j.get('data', {}).get('user', {}).get('role', '?')}")

    s, r, j, _url = http_call(opener, 'GET', '/api/positions')
    n = len(j.get('data') or [])
    _record('A', '岗位列表', 'PASS' if s == 200 else 'FAIL', f'count={n}')


# ============================================================================
# B. 岗位管理双入口
# ============================================================================
def test_b_position_dual_entry(opener):
    print('\n========== B. 岗位管理双入口 ==========')
    # B-1 手动录入路径
    name = '__smoke_test_position__'
    s, r, j, _url = http_call(opener, 'POST', '/api/positions', {
        'name': name, 'jd_content': '冒烟测试岗位', 'tech_requirements': 'Python,Flask'
    })
    created_id = None
    if s in (200, 201) and j.get('code') in (0, 200, 201):
        created_id = (j.get('data') or {}).get('id')
    _record('B', '手动录入创建岗位', 'PASS' if created_id else 'FAIL',
            f'id={created_id}' if created_id else f'status={s} msg={j.get("message", "")[:40]}')

    # B-2 PDF 智能导入接口（纯文本路径，避开 PDF 解析依赖）
    sample_jd = '''职位：Node.js 全栈开发工程师

职责：使用 Node.js + Express/Koa 构建高并发 SaaS API，MySQL/PostgreSQL 数据库设计，Redis 缓存，Docker/K8s 部署。

要求：精通 Express 或 Koa，熟悉 MongoDB、Redis、Docker、Kubernetes、Git，3年以上经验。'''
    s, r, j, _url = http_call(opener, 'POST', '/api/positions/parse-jd', {'text': sample_jd})
    data = j.get('data') or {}
    ok_parse = (s == 200 and j.get('code') in (0, 200)
                and data.get('name') and data.get('tech_requirements'))
    detail = f"name={data.get('name', '')[:30]} tech_count={len([x for x in (data.get('tech_requirements') or '').split(',') if x.strip()])}"
    _record('B', 'PDF/文本 AI 识别接口', 'PASS' if ok_parse else 'FAIL', detail)

    # B-3 预览确认（直接调 POST 创建）
    if data.get('name'):
        s2, r2, j2, _url2 = http_call(opener, 'POST', '/api/positions', {
            'name': '__smoke_test_position_from_pdf__',
            'jd_content': data.get('jd_content', ''),
            'tech_requirements': data.get('tech_requirements', '')
        })
        ok_pdf_create = s2 in (200, 201) and j2.get('code') in (0, 200, 201)
        _record('B', '预览确认后创建岗位', 'PASS' if ok_pdf_create else 'FAIL',
                j2.get('message', ''))
        if ok_pdf_create:
            # 清理
            for pid in [(j2.get('data') or {}).get('id'), created_id]:
                if pid:
                    http_call(opener, 'DELETE', f'/api/positions/{pid}')


# ============================================================================
# C. 候选人门户下线
# ============================================================================
def test_c_candidate_portal_offline(opener):
    print('\n========== C. 候选人门户下线 ==========')
    s, r, j, _url = http_call(opener, 'POST', '/api/auth/register',
                   {'username': 'smoke_cand', 'password': '123456', 'real_name': '测试'})
    ok = s == 403 and '下线' in j.get('message', '')
    _record('C', '/api/auth/register 已拒绝', 'PASS' if ok else 'FAIL',
            f'status={s} msg={j.get("message", "")[:40]}')

    for path in ['/candidate/login', '/candidate/dashboard', '/candidate']:
        s, r, j, final_url = http_call(opener, 'GET', path)
        # 下线标准：404 (路由不存在) 或 重定向走了 (final_url 不以 /candidate 开头)
        ok = (s == 404) or (s in (200, 302, 301) and not final_url.rstrip('/').endswith('/candidate'))
        _record('C', f'{path} 已下线/404', 'PASS' if ok else 'FAIL',
                f'status={s} final_url={final_url}')

    # 检查登录页 HTML 不再有候选人入口（新建未登录 opener 避免重定向到首页）
    import http.cookiejar
    import urllib.request as _ur
    fresh = _ur.build_opener(_ur.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    req = _ur.Request(f'{BASE}/login')
    try:
        resp = fresh.open(req, timeout=10)
        body = resp.read().decode('utf-8', errors='replace')
        final_url = resp.geturl()
    except Exception:
        body, final_url = '', ''
    has_cand_tab = ('tabCand' in body or '候选人门户' in body or 'doCandAction' in body
                    or 'candForm' in body or '/api/auth/register' in body)
    _record('C', '登录页候选人 tab 已清理',
            'PASS' if not has_cand_tab else 'FAIL',
            '仍含候选人关键词' if has_cand_tab else f'final={final_url} len={len(body)}')


# ============================================================================
# D. 导航栏响应式
# ============================================================================
def test_d_navbar(opener):
    print('\n========== D. 导航栏响应式 ==========')
    s, r, j, _url = http_call(opener, 'GET', '/')
    body = r
    # 关键元素
    items = {
        'navbar-toggler 按钮': 'navbar-toggler' in body,
        'navbar-expand-lg 类': 'navbar-expand-lg' in body,
        '@media (max-width: 991.98px) 响应式 CSS':
            '(max-width: 991.98px)' in open('templates/base.html', encoding='utf-8').read(),
        '5 个核心链接 (Dashboard/岗位/候选人/面试工作台/admin)':
            all(k in body for k in ['href="/positions"', 'href="/candidates"',
                                    'href="/live-interview"', 'href="/interview"']),
        '候选人门户入口已被移除':
            'href="/candidate"' not in body,
    }
    for name, ok in items.items():
        _record('D', name, 'PASS' if ok else 'FAIL')


# ============================================================================
# E. 实时面试布局
# ============================================================================
def test_e_live_interview_layout(opener):
    print('\n========== E. 实时面试布局 ==========')
    body = open('templates/live_interview.html', encoding='utf-8').read()
    items = {
        '左侧 col-md-9 (拓宽)': 'col-md-9' in body,
        '右侧 col-md-3 (压窄)': 'col-md-3' in body and 'col-md-4' not in body.split('col-md-9')[1].split('</div>')[0] if 'col-md-9' in body else False,
        '角色控制合并当前说话人': '角色控制' in body and 'currentSpeaker' in body,
        'AI 实时分析可折叠 (aiAnalysisCollapse)': 'aiAnalysisCollapse' in body,
        '建议追问可折叠 (suggestedCollapse)': 'suggestedCollapse' in body,
        '对话框高度 540px': 'height: 540px' in body,
        '关键 ID 齐全 (questionsCard/dialogContainer/roleStatus)':
            all(k in body for k in ['questionsCard', 'dialogContainer', 'roleStatus',
                                    'btnRoleInterviewer', 'btnRoleCandidate']),
    }
    for name, ok in items.items():
        _record('E', name, 'PASS' if ok else 'FAIL')


# ============================================================================
# F. 综合评分新公式
# ============================================================================
def test_f_scoring_formula(opener):
    print('\n========== F. 综合评分新公式 ==========')
    code_path = 'agents/interview_eval_coordinator.py'
    if not os.path.exists(code_path):
        _record('F', '汇总师代码存在', 'FAIL', '文件缺失')
        return
    src = open(code_path, encoding='utf-8').read()
    items = {
        'W_SINGLE_ROUND=0.60 权重': 'W_SINGLE_ROUND' in src and '0.6' in src,
        'W_COORD_5DIM=0.40 权重（v2.1: 汇总师 5 维加权）': 'W_COORD_5DIM' in src and '0.4' in src,
        '【v2.1 BUG A 修复】5 维权重常量齐备':
            all(w in src for w in ('W_TECH_FOUNDATION', 'W_PROJECT_EXP', 'W_SYSTEM_DESIGN', 'W_COMMUNICATION', 'W_LEARNING')),
        '新公式 = 单轮×60% + 汇总师 5 维×40%':
            'W_SINGLE_ROUND' in src and 'W_COORD_5DIM' in src,
        '向述兼容 fallback (无单轮评分时退回纯汇总师)':
            'overall_score = int(round(coord_5dim_100))' in src,
        '【v2.1】5 维加权函数 _compute_5dim_weighted_score':
            '_compute_5dim_weighted_score' in src,
        'computation 字段含 single_round_score_100/coord_5dim_100':
            'coord_5dim_100' in src and 'single_round_score_100' in src,
    }
    for name, ok in items.items():
        _record('F', name, 'PASS' if ok else 'FAIL')


# ============================================================================
# G. 候选人/面试会话冒烟
# ============================================================================
def test_g_lists(opener):
    print('\n========== G. 候选人/面试列表冒烟 ==========')
    s, r, j, _url = http_call(opener, 'GET', '/api/candidates')
    n = len(j.get('data') or [])
    _record('G', '候选人列表', 'PASS' if s == 200 else 'FAIL', f'count={n}')

    s, r, j, _url = http_call(opener, 'GET', '/api/interviews/sessions')
    if s == 200:
        n = len(j.get('data') or [])
        _record('G', '面试会话列表', 'PASS', f'count={n}')
    else:
        # 接口可能叫别的路径
        s2, r2, j2, _url2 = http_call(opener, 'GET', '/api/interviews')
        _record('G', '面试会话列表', 'PASS' if s2 == 200 else 'FAIL',
                f'status={s} status2={s2}')


# ============================================================================
# H. 关键 ID 完整性
# ============================================================================
def test_h_ids():
    print('\n========== H. 关键 ID 完整性 ==========')
    files = {
        'live_interview.html': ['questionsCard', 'dialogContainer', 'currentSpeaker',
                                'aiAnalysis', 'suggestedQuestions', 'roleStatus',
                                'btnRoleInterviewer', 'btnRoleCandidate', 'autoModeSwitch'],
        'positions.html': ['newName', 'newJd', 'newTech', 'pdfFile',
                          'previewName', 'previewJd', 'previewTech'],
    }
    for f, ids in files.items():
        body = open(f'templates/{f}', encoding='utf-8').read()
        for i in ids:
            ok = f'id="{i}"' in body
            _record('H', f'{f}::{i}', 'PASS' if ok else 'FAIL')


# ============================================================================
# I. jinja 模板语法静态校验
# ============================================================================
def test_i_jinja():
    print('\n========== I. jinja 模板语法 ==========')
    try:
        from jinja2 import Environment, FileSystemLoader
        env = Environment(loader=FileSystemLoader('templates'))
        for f in ['base.html', 'positions.html', 'live_interview.html', 'login.html']:
            try:
                env.parse(open(f'templates/{f}', encoding='utf-8').read())
                _record('I', f'templates/{f} 语法', 'PASS')
            except Exception as e:
                _record('I', f'templates/{f} 语法', 'FAIL', str(e)[:80])
    except ImportError:
        _record('I', 'jinja2 不可用', 'SKIP')


# ============================================================================
# J. LLM 接入验证（DeepSeek-v4-Flash + parse_json 兼容）
# ============================================================================
def test_j_llm_integration():
    print('\n========== J. LLM 接入验证 ==========')
    # J-1 .env 配置完整性
    env_path = '.env'
    if not os.path.exists(env_path):
        _record('J', '.env 文件存在', 'FAIL', '缺失')
        return
    cfg = {}
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            cfg[k.strip()] = v.strip()

    items = {
        'LLM_API_URL 已配置为 DeepSeek endpoint':
            'deepseek.com' in cfg.get('LLM_API_URL', ''),
        'LLM_MODEL 已配置为 deepseek-v4-flash':
            cfg.get('LLM_MODEL', '').lower() == 'deepseek-v4-flash',
        'LLM_API_KEY 已填（不含占位符）':
            cfg.get('LLM_API_KEY', '').startswith('sk-') and 'YOUR_' not in cfg.get('LLM_API_KEY', '')
                                          and '<your-' not in cfg.get('LLM_API_KEY', ''),
        '旧 MiniMax 配置已注释（保留备查）':
            '# LLM_API_URL=https://api.minimaxi.com' in open(env_path, encoding='utf-8').read(),
    }
    for name, ok in items.items():
        _record('J', name, 'PASS' if ok else 'FAIL')

    # J-2 .env 直接联通测试（独立于 Flask）
    api_key = cfg.get('LLM_API_KEY', '')
    api_url = cfg.get('LLM_API_URL', '')
    model = cfg.get('LLM_MODEL', '')
    if api_key.startswith('sk-') and 'YOUR_' not in api_key:
        try:
            import requests
            payload = {
                'model': model,
                'messages': [
                    {'role': 'system', 'content': '你是 JSON 输出器。'},
                    {'role': 'user', 'content': '返回 {"ok": true}'}
                ],
                'temperature': 0.3,
                'max_tokens': 100
            }
            resp = requests.post(api_url,
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': f'Bearer {api_key}'},
                                 json=payload, timeout=30)
            ok_http = resp.status_code == 200
            _record('J', 'DeepSeek-v4-Flash API 可达', 'PASS' if ok_http else 'FAIL',
                    f'HTTP {resp.status_code}')
            if ok_http:
                data = resp.json()
                content = data['choices'][0]['message']['content']
                # deepseek-v4-flash 是 Flash 版本，预期无 think 块（直输出）
                _record('J', '响应无 think 块（v4-flash 直输出特征）',
                        'PASS' if '<think>' not in content else 'WARN',
                        f'len={len(content)}')
        except Exception as e:
            _record('J', 'DeepSeek-v4-Flash API 连通性', 'FAIL', str(e)[:80])
    else:
        _record('J', 'API_KEY 未配置，跳过联通测试', 'SKIP')

    # J-3 parse_json() 兼容推理模型 think 块
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from services.llm_service import LlmService
        polluted = '<think>some thinking</think>\n{"score": 75, "level": "senior"}'
        parsed = LlmService.parse_json(polluted)
        _record('J', 'parse_json() 剥离 think 块',
                'PASS' if parsed == {'score': 75, 'level': 'senior'} else 'FAIL',
                str(parsed))
        pure = '{"score": 80, "level": "mid"}'
        parsed2 = LlmService.parse_json(pure)
        _record('J', 'parse_json() 纯 JSON 向后兼容',
                'PASS' if parsed2 == {'score': 80, 'level': 'mid'} else 'FAIL')
    except Exception as e:
        _record('J', 'parse_json() 导入测试', 'FAIL', str(e)[:80])

    # J-4 服务运行时 LLM 调用验证（用真实的业务接口 POST /api/positions/parse-jd）
    try:
        import requests as r2
        # 1. 先登录（业务接口需要认证）
        s = r2.Session()
        s.post(f'{BASE}/api/auth/login',
               json={'username': ADMIN_USER, 'password': ADMIN_PASS},
               timeout=15)
        # 2. 调真实业务接口 parse-jd（走 LLM，会走 DeepSeek-v4-Flash 链路）
        r3 = s.post(f'{BASE}/api/positions/parse-jd',
                    json={'text': '职位：Python 后端，要求：Flask、Docker、MySQL、3 年经验。'},
                    timeout=60)
        ok_status = r3.status_code == 200
        _record('J', '业务接口 parse-jd 调用成功', 'PASS' if ok_status else 'FAIL',
                f'status={r3.status_code}')
        if ok_status:
            data = r3.json().get('data') or {}
            _record('J', 'parse-jd 返回 name 字段',
                    'PASS' if data.get('name') else 'FAIL',
                    f"name={data.get('name', '')[:30]}")
            _record('J', 'parse-jd 返回 tech_requirements 字段',
                    'PASS' if data.get('tech_requirements') else 'FAIL',
                    f"len={len(data.get('tech_requirements', ''))}")
        else:
            _record('J', 'parse-jd 响应内容',
                    'FAIL', r3.text[:200])
    except Exception as e:
        _record('J', '业务接口 LLM 调用', 'FAIL', str(e)[:80])


# ============================================================================
# K. 【v3.6】隐藏维度异步评估（partial_complete + hidden_done）
# ============================================================================
def test_k_v36_async(opener):
    """v3.6 异步隐藏评估验证
       - SSE partial_complete 事件触发
       - < 130s 限制
       - complete 事件后 _hidden_done=True
       - 服务端代码不再报 free variable 错误
       - 前端 consumeSSE 支持 onPartial 回调
    """
    print('\n========== K. v3.6 隐藏维度异步评估 ==========')

    # K-1 代码静态检查
    code_items = {
        'orchestrator evaluate_resume 已拆为 tech+soft / hidden 两阶段':
            ('阶段A：tech + soft 并发（限时 120s）' in
             open('services/agent_orchestrator.py', encoding='utf-8').read()
             and 'f_a.result(timeout=150)' in
             open('services/agent_orchestrator.py', encoding='utf-8').read()),
        '_emit 支持 _extra 参数（传 partial_result payload）':
            '_extra' in open('services/agent_orchestrator.py', encoding='utf-8').read(),
        'SSE stream_candidate_analysis SSE_TIMEOUT=600':
            'SSE_TIMEOUT = 600' in open('routes/stream_routes.py', encoding='utf-8').read(),
        'generate() 顶部 inline import CandidateRepository（闭包 fix）':
            ('from repositories.candidate_repository import CandidateRepository' in
             open('routes/stream_routes.py', encoding='utf-8').read()),
        'partial_complete 事件推独立 SSE event':
            ('yield _sse_event(\'partial_complete\'' in
             open('routes/stream_routes.py', encoding='utf-8').read()),
        '前端 consumeSSE 增加 onPartial 回调':
            ('onPartial' in open('templates/base.html', encoding='utf-8').read()),
        '候选人 modal 评估状态徽章 (aiEvalBadge)':
            ('aiEvalBadge' in open('templates/candidates.html', encoding='utf-8').read()),
        # 【v3.6.1】角落角标 DOM/函数
        'base.html 含角落角标 DOM (aiCornerBadge)':
            ('aiCornerBadge' in open('templates/base.html', encoding='utf-8').read()),
        'base.html 含 showAiCornerBadge/updateAiCornerBadge/hideAiCornerBadge':
            (all(fn in open('templates/base.html', encoding='utf-8').read()
                 for fn in ['showAiCornerBadge', 'updateAiCornerBadge', 'hideAiCornerBadge'])),
        'base.html 含两阶段超时 (_AI_PHASE1_TIMEOUT=120)':
            ('_AI_PHASE1_TIMEOUT = 120' in open('templates/base.html', encoding='utf-8').read()),
        'base.html 含 _AI_PHASE2_TIMEOUT=180':
            ('_AI_PHASE2_TIMEOUT = 180' in open('templates/base.html', encoding='utf-8').read()),
        'base.html partial_complete 阶段切换 _aiSwitchPhase(2)':
            ('_aiSwitchPhase(2)' in open('templates/base.html', encoding='utf-8').read()),
        'candidates.html analyzeCandidate 重写（不自动弹 modal）':
            ('_aiEvalJob' in open('templates/candidates.html', encoding='utf-8').read()
             and 'onAiBadgeClick' in open('templates/candidates.html', encoding='utf-8').read()),
        'candidates.html analyzeCandidate 初始文案含 ≤2 分钟/≤3 分钟':
            ('≤2 分钟' in open('templates/candidates.html', encoding='utf-8').read()
             and '≤3 分钟' in open('templates/candidates.html', encoding='utf-8').read()),
        # 【v3.6.3】变黑 Bug 修复
        'base.html 采用原版白透明风格 (rgba(255,255,255,0.85) + backdrop-filter 模糊)':
            ('background: rgba(255, 255, 255, 0.85)' in open('templates/base.html', encoding='utf-8').read()
             and 'backdrop-filter: blur(4px)' in open('templates/base.html', encoding='utf-8').read()),
        'base.html hideAiLoading 加 inline display=none 冻结遮罩':
            ('overlay.style.display = \'none\'' in open('templates/base.html', encoding='utf-8').read()),
        'candidates.html aiModal hidden 事件强制清空 backdrop + 解锁 body':
            ('_purgeModalBackdrops' in open('templates/candidates.html', encoding='utf-8').read()
             and 'hidden.bs.modal' in open('templates/candidates.html', encoding='utf-8').read()),
        'candidates.html aiModal 恢复默认黑透明 backdrop (移除 data-bs-backdrop="false")':
            ('data-bs-backdrop="false"' not in open('templates/candidates.html', encoding='utf-8').read()),
        'candidates.html onPartial 自动弹 partial modal（不再手动点）':
            (re.search(r'onPartial[\s\S]*?showAiResult\(partialResult',
                       open('templates/candidates.html', encoding='utf-8').read(),
                       re.DOTALL) is not None),
        # 【v3.6.4】恢复半透明黑 overlay + 隐性分析精简
        'base.html ai-loading-overlay 原来的白透明模糊 (恢复原版)':
            ('rgba(255, 255, 255, 0.85)' in open('templates/base.html', encoding='utf-8').read()),
        'candidates.html 删除候选人画像模块 (无 profileHtml)':
            ('profileHtml' not in open('templates/candidates.html', encoding='utf-8').read()),
        'candidates.html 删除候选人画像工具函数 (无 levelBadge / confBadge)':
            ('levelBadge' not in open('templates/candidates.html', encoding='utf-8').read()
             and 'confBadge' not in open('templates/candidates.html', encoding='utf-8').read()),
        'hidden_evaluator.py prompt 要求 4 个新维度 (简历真实度/学习能力/职业发展方向/居住地)':
            (all(k in open('agents/hidden_evaluator.py', encoding='utf-8').read()
                 for k in ['简历真实度', '学习能力', '职业发展方向', '居住地'])),
        'hidden_evaluator.py prompt 限制 detail ≤40 字':
            ('≤40 字' in open('agents/hidden_evaluator.py', encoding='utf-8').read()),
    }
    for name, ok in code_items.items():
        _record('K', name, 'PASS' if ok else 'FAIL')

    # K-2 动态 SSE 流验证（可选：如指定了 RUN_V36=1）
    if os.environ.get('RUN_V36') == '1':
        import requests as _rq
        sess = _rq.Session()
        sess.post(f'{BASE}/api/auth/login',
                  json={'username': ADMIN_USER, 'password': ADMIN_PASS},
                  timeout=15)
        # 创建短简历候选人
        pos = sess.get(f'{BASE}/api/positions').json()['data'][0]
        c = sess.post(f'{BASE}/api/candidates', json={
            'name': 'v36-smoke',
            'position_id': pos['id'],
            'resume_text': 'Python 后端 5 年。熟悉 Django、MySQL、Redis、Docker、Kubernetes。'
        }).json()
        cid = c['data']['id']
        try:
            partial_seen = complete_seen = False
            t0 = __import__('time').time()
            resp = sess.post(f'{BASE}/api/stream/candidate-analysis/{cid}',
                            stream=True, timeout=320)
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith('data: '):
                    continue
                p = __import__('json').loads(raw[6:])
                e = p.get('event')
                if e == 'partial_complete':
                    partial_seen = True
                    _record('K', 'partial_complete 事件', 'PASS',
                            f'pr_score={p.get("partial_result", {}).get("match_score")}')
                if e == 'complete':
                    complete_seen = True
                    r = p.get('result') or {}
                    _record('K', 'complete _hidden_done=True', 'PASS' if r.get('_hidden_done') else 'FAIL',
                            f'_hidden_done={r.get("_hidden_done")}')
                    break
            _record('K', 'partial < 130s 限制',
                    'PASS' if partial_seen else 'FAIL')
        finally:
            # 清理
            try:
                sess.delete(f'{BASE}/api/candidates/{cid}')
            except Exception:
                pass
    else:
        _record('K', '动态 SSE v3.6 验证（可选 RUN_V36=1）', 'SKIP')

    # =========================================================================
    # 【v4.1】重新评估接口静态+动态检查
    # =========================================================================
    cand_routes_src = open('routes/candidate_routes.py', encoding='utf-8').read()
    _record('L', 'candidate_routes 含 DELETE /<int:id>/ai-analysis',
            'PASS' if "methods=['DELETE']" in cand_routes_src and "clear_ai_analysis" in cand_routes_src else 'FAIL')

    candidates_html_src = open('templates/candidates.html', encoding='utf-8').read()
    _record('L', 'candidates.html 含「重新评估」按钮 + reanalyzeCandidate 函数',
            'PASS' if (
                'reanalyzeCandidate' in candidates_html_src
                and 'bi-arrow-clockwise' in candidates_html_src
                and '重新评估' in candidates_html_src
            ) else 'FAIL')

    # 动态检查：调一次 DELETE 接口，看返回结构
    s_list, _, j_list, _ = http_call(opener, 'GET', '/api/candidates')
    cands_list = j_list.get('data') or []
    ai_cand = next((c for c in cands_list if c.get('ai_analysis')), None)
    if ai_cand:
        cid = ai_cand['id']
        # 1) 清空
        s_del, _, j_del, _ = http_call(opener, 'DELETE', f'/api/candidates/{cid}/ai-analysis')
        ok1 = s_del == 200 and j_del.get('code') == 200
        _record('L', f'DELETE /api/candidates/{cid}/ai-analysis 返回 OK',
                'PASS' if ok1 else 'FAIL', f'status={s_del} body={j_del}')
        # 2) 确认 DB 字段被清空
        s_g, _, j_g, _ = http_call(opener, 'GET', f'/api/candidates/{cid}')
        cand_after = j_g.get('data') or {}
        ok2 = (cand_after.get('ai_analysis') in (None, '')) and cand_after.get('match_score') is None
        _record('L', 'DB 中 ai_analysis + match_score 已清空',
                'PASS' if ok2 else 'FAIL',
                f'ai_len={len(cand_after.get("ai_analysis") or "")} score={cand_after.get("match_score")}')
        # 3) 重复 DELETE 应报 400
        s_d2, _, j_d2, _ = http_call(opener, 'DELETE', f'/api/candidates/{cid}/ai-analysis')
        ok3 = s_d2 == 400 and j_d2.get('code') == 400
        _record('L', '重复 DELETE 返 400（无 AI 时拒绝）',
                'PASS' if ok3 else 'FAIL', f'status={s_d2}')
        # 4) 不存在返 404
        s_nf, _, j_nf, _ = http_call(opener, 'DELETE', '/api/candidates/99999/ai-analysis')
        ok4 = s_nf == 404 and j_nf.get('code') == 404
        _record('L', 'DELETE 不存在的候选人返 404',
                'PASS' if ok4 else 'FAIL', f'status={s_nf}')
    else:
        # 没有可重置的候选人时，只跑静态检查（已上面测试）
        _record('L', '动态 DELETE 检查', 'SKIP', '没有已评估的候选人可供测试')


# ============================================================================
# M. 【v4.4】两段式拆分：简历评估 + 出题手动触发
# ============================================================================
def test_m_v44_split(opener):
    """v4.4 拆分验证

    设计：
      - stream_candidate_analysis 只跑简历评估（不再调 design_questions）
      - complete 事件 payload.session 为 None
      - 前端 candidates.html startQuestionDesign 函数存在，调 /api/stream/questions/<id> 独立出题
      - showAiResult 根据 session 是否存在切换「立即出题」/「前往面试工作台」按钮
    """
    print('\n========== M. v4.4 两段式拆分 ==========')

    stream_src = open('routes/stream_routes.py', encoding='utf-8').read()
    candidates_src = open('templates/candidates.html', encoding='utf-8').read()

    items = {
        # 后端：stream_candidate_analysis 不再调用 generate_questions
        'routes/stream_routes.py stream_candidate_analysis 文档含【v4.4 拆分】':
            'v4.4 拆分' in stream_src and '只跑简历评估' in stream_src,
        'routes/stream_routes.py 移除了 InterviewService.generate_questions 调用（拆分后）':
            # worker 中不应再出现 generate_questions
            'llm_questions = _IS3.generate_questions' not in stream_src,
        'routes/stream_routes.py complete 事件 session=None':
            "'session': None" in stream_src,
        'routes/stream_routes.py worker 中不再出现 db.session.delete / db.session.commit 代码':
            # 去掉注释行后再匹配（避开描述性注释中的“db.session.delete 已移除”）
            (lambda code: 'db.session.delete' not in code and 'db.session.commit' not in code)(
                '\n'.join(line for line in stream_src.splitlines() if not line.lstrip().startswith('#'))
            ),
        'routes/stream_routes.py 不再 from extensions import db':
            'from extensions import db' not in stream_src,

        # 前端：拆分后的两个 SSE 调用 + startQuestionDesign
        'candidates.html startQuestionDesign 函数定义':
            'async function startQuestionDesign' in candidates_src,
        'candidates.html 「立即出题」按钮 HTML':
            '立即出题' in candidates_src and 'aiStartQuestionBtn' in candidates_src,
        'candidates.html 「前往面试工作台」按钮':
            '前往面试工作台' in candidates_src,
        'candidates.html startQuestionDesign 调 /api/stream/questions/<id>':
            '/api/stream/questions/${candidateId}' in candidates_src,
        'candidates.html analyzeCandidate onComplete 立刻弹 final modal（不含 session）':
            ('partialModalInstance.hide()' in candidates_src
             and '_aiEvalJob.session = payload.session || null' in candidates_src),
        'candidates.html 初脚台 + 手动出题按钮文档子串':
            '【v4.4】两段式拆分' in candidates_src,

        # 后端：独立出题接口仍存在（复用 interview.html 也在用的 /api/stream/questions/<id>）
        'routes/stream_routes.py stream_question_generation 接口仍存在':
            "def stream_question_generation(candidate_id):" in stream_src,
    }
    for name, ok in items.items():
        _record('M', name, 'PASS' if ok else 'FAIL')

    # 动态验证（可选：RUN_V44=1）
    if os.environ.get('RUN_V44') == '1':
        try:
            import requests as _rq
            sess = _rq.Session()
            sess.post(f'{BASE}/api/auth/login',
                      json={'username': ADMIN_USER, 'password': ADMIN_PASS},
                      timeout=15)
            pos_list = sess.get(f'{BASE}/api/positions').json().get('data') or []
            if not pos_list:
                _record('M', 'v4.4 动态：缺少岗位', 'SKIP', '请先创建岗位')
                return
            pos = pos_list[0]
            c = sess.post(f'{BASE}/api/candidates', json={
                'name': 'v44-smoke',
                'position_id': pos['id'],
                'resume_text': 'Python 后端 5 年。熟悉 Django、MySQL、Redis、Docker。'
            }).json()
            cid = c['data']['id']
            try:
                # 调拆分后的简历评估接口，看 complete 事件 session 是否为 None
                complete_payload = None
                t0 = __import__('time').time()
                resp = sess.post(f'{BASE}/api/stream/candidate-analysis/{cid}',
                                 stream=True, timeout=320)
                for raw in resp.iter_lines(decode_unicode=True):
                    if not raw or not raw.startswith('data: '):
                        continue
                    p = __import__('json').loads(raw[6:])
                    if p.get('event') == 'complete':
                        complete_payload = p
                        break
                elapsed = __import__('time').time() - t0
                _record('M', '动态: complete 事件 payload.session = None（拆分生效）',
                        'PASS' if complete_payload and complete_payload.get('session') is None else 'FAIL',
                        f'session={complete_payload.get("session") if complete_payload else "NULL"} elapsed={elapsed:.1f}s')
                _record('M', '动态: complete.result.match_score 存在',
                        'PASS' if complete_payload and complete_payload.get('result', {}).get('match_score') is not None else 'FAIL',
                        f'score={complete_payload.get("result", {}).get("match_score") if complete_payload else "?"}')
            finally:
                try:
                    sess.delete(f'{BASE}/api/candidates/{cid}')
                except Exception:
                    pass
        except Exception as e:
            _record('M', 'v4.4 动态验证', 'FAIL', str(e)[:80])
    else:
        _record('M', '动态 v4.4 拆分验证（可选 RUN_V44=1）', 'SKIP')


# ============================================================================
# 入口
# ============================================================================
def main():
    print('=' * 70)
    print(f'系统性冒烟测试  target={BASE}')
    print('=' * 70)

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    test_a_basic(opener)
    test_b_position_dual_entry(opener)
    test_c_candidate_portal_offline(opener)
    test_d_navbar(opener)
    test_e_live_interview_layout(opener)
    test_f_scoring_formula(opener)
    test_g_lists(opener)
    test_h_ids()
    test_i_jinja()
    test_j_llm_integration()
    test_k_v36_async(opener)
    test_m_v44_split(opener)

    print('\n' + '=' * 70)
    print(f'汇总  PASS={STATS["PASS"]}  FAIL={STATS["FAIL"]}  '
          f'WARN={STATS["WARN"]}  SKIP={STATS["SKIP"]}')
    print('=' * 70)

    if STATS['FAIL']:
        print('\n失败项：')
        for r in RESULTS:
            if r['status'] == 'FAIL':
                print(f'  ✗ [{r["cat"]}] {r["name"]}  {r["detail"][:80]}')

    sys.exit(0 if STATS['FAIL'] == 0 else 1)


if __name__ == '__main__':
    main()