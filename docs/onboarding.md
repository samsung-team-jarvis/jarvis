# 팀원 온보딩 체크리스트

처음 합류할 때 한 번 끝내는 절차다. 다 끝나면 [온보딩 이슈 #7](https://github.com/samsung-team-jarvis/jarvis/issues/7)에 체크하고 댓글로 알린다.

## 1. 계정

- [ ] GitHub org `samsung-team-jarvis` 초대 수락 (메일 또는 https://github.com/orgs/samsung-team-jarvis)
- [ ] 수락 후 저장소 **Write 권한**이 있는지 확인 (jarvis 저장소 화면에 Settings 탭은 없어도 브랜치 push가 되면 OK). 안 되면 현종에게 요청
- [ ] 팀 공유 Drive 폴더 접근 수락 (데이터·모델 파일 저장소, 링크는 팀 메신저)

## 2. PC 준비

필요한 것: git, Python 3.10 이상. Windows는 PowerShell에서 `py` 명령을 쓴다.

```bash
git config --global user.name "이름"
git config --global user.email "GitHub 계정 이메일"   # 다르면 커밋 기록(잔디)이 본인 계정에 안 남는다

git clone https://github.com/samsung-team-jarvis/jarvis.git
cd jarvis
python3 scripts/setup.py          # Windows: py scripts\setup.py
```

`setup.py`가 하는 일: 가상환경(.venv) 생성 → 개발 도구 설치 → git 훅 설치 → 빠른 검사.
마지막에 ✅만 보이면 성공. ❌가 있으면 팀 메신저에 출력 결과를 올린다.

## 3. AI 도구 (쓰는 것만)

모든 도구가 `AGENTS.md`(작업 규칙)를 읽도록 이미 설정되어 있다. 도구별로 한 번만 확인할 것:

| 도구 | 확인할 것 |
|---|---|
| Claude Code | 없음. 세션 시작 시 훅이 없으면 경고가 뜬다 |
| Codex | repo를 처음 열 때 프로젝트 `.codex/` **신뢰(trust)** 를 승인 |
| Gemini CLI | 없음 |
| Cursor | Settings에서 "Include Third-Party Plugins, Skills, and Other Configs"가 켜져 있는지 |
| Copilot (VS Code) | `chat.useAgentsMdFile` 켜기. 가능하면 `chat.useClaudeHooks`도 |
| 기타 | [AI 도구별 설정](./agent/tools.md) |

AI 도구에 작업을 시킬 때는 **작업 ID로 지시**하면 규칙대로 진행한다. 예: "STT-01 작업 시작해줘".

## 4. 꼭 읽을 문서 (15분)

- [Git Convention](./conventions/git.md) — 이슈 → 브랜치 → PR → 머지, 이름 형식
- [PLAN](./PLAN.md) — 해야 할 작업 목록. 맡을 작업을 고른다
- [Architecture Overview](./architecture/overview.md) — 전체 구조, 안전 규칙

규칙 요약:
- `main`에 직접 push 불가. 모든 작업은 이슈 → 브랜치 → PR.
- PR을 열면 담당자·라벨·리뷰 요청이 자동으로 붙는다. 리뷰 요청이 오면 확인해 준다.
- PR은 **리뷰 승인 1개 + CI 통과** 후 머지.
- 측정하지 않은 수치는 문서에 쓰지 않는다.
- 검사가 실패하면 `--no-verify`로 우회하지 말고 형식을 고친다.

## 5. 완료 보고

- [ ] [결정 대기 질문](./decisions/open-questions.md) 중 본인이 답할 수 있는 것에 답하기 — 특히 Q-03(본인 PC: x86/ARM, GPU 유무), Q-04(맡고 싶은 워크스트림)
- [ ] [온보딩 이슈 #7](https://github.com/samsung-team-jarvis/jarvis/issues/7)에 본인 항목 체크 + 댓글 (형식은 이슈 본문 참고)

## 팀원 GitHub 아이디

| 이름 | GitHub |
|---|---|
| 신지호 (팀장) | `SJH0428` |
| 이현종 | `Navi-Up` |
| 최지환 | `spaceImage` |
| 최석진 | `pleine1279` |
