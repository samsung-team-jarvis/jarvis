---
name: verify-agent-docs
description: AGENTS.md, CLAUDE.md, docs, skills, recipes, templates를 추가·이동·수정한 뒤 링크 깨짐과 인덱스 누락을 점검할 때 사용합니다.
---

# Agent 문서 검증

## 점검 항목

1. **링크 깨짐**: 문서 안의 상대 경로 링크가 실제 파일을 가리키는지
2. **인덱스 누락**: `docs/`, `recipes/`, `templates/`, `.claude/skills/`의 모든 파일이 `docs/index.md`에서 도달 가능한지
3. **구조 일치**: `docs/agent/index.md`의 Current Shape가 실제 `.claude/skills` 목록과 같은지
4. **중복 규칙**: `AGENTS.md`·`CLAUDE.md`에 세부 규칙 원문이 복사되어 있지 않은지
5. **옛 경로**: 이동·삭제된 문서 경로가 남아 있지 않은지
6. **Codex 링크**: `.agents/skills`가 `.claude/skills`를 가리키는 심볼릭 링크인지

## 명령

```bash
# 문서 목록 vs index 비교
find docs recipes templates .claude/skills -name '*.md' | sort
grep -o '([^)]*\.md)' docs/index.md | sort

# 상대 링크 대상 존재 확인 (각 md 파일 기준 경로로 해석)
python3 - <<'PY'
import re, pathlib
bad = []
for md in pathlib.Path('.').rglob('*.md'):
    if any(p in md.parts for p in ('.git', 'node_modules', '.venv')):
        continue
    for link in re.findall(r'\]\(([^)#\s]+)', md.read_text(encoding='utf-8')):
        if link.startswith(('http', 'mailto:')):
            continue
        if not (md.parent / link).exists():
            bad.append(f'{md}: {link}')
print('\n'.join(bad) or 'OK: 깨진 링크 없음')
PY

# Codex skill 링크
ls -l .agents/skills

git diff --check
```

## 결과 보고

- 깨진 링크·누락 문서 목록과 수정 내역
- 실행한 명령과 결과
