"""DOMJudge 대회 결과를 Spotboard용 정적 스코어보드로 내보내기.

사용 예 (Windows PowerShell):
    $env:DOMJUDGE_USER = 'reader'
    $env:DOMJUDGE_PASS = '비밀번호'
    python export.py --url https://contest.solutio.page --cid KGUPC-2-Beginner-R --out kgupc/2026/beginner --webapp spotboard-webapp

- 표준 라이브러리만 사용 (pip 설치 불필요)
- --webapp: 압축 푼 Spotboard 웹앱 폴더. --out 폴더에 index.html이 없을 때만 복사
- contest.json / runs.json 은 실행할 때마다 새로 생성
- award_slide.json 은 없을 때만 빈 목록으로 생성 (수상 정보는 직접 채우기)
"""
import argparse
import base64
import getpass
import json
import os
import shutil
import sys
import urllib.error
import urllib.request

CONFIG_OVERRIDE_MARK = "/* === export.py overrides === */"
CONFIG_OVERRIDE = CONFIG_OVERRIDE_MARK + """
config.apiBase = './';
config.path['award_slide.json'] = './award_slide.json';
config.path['events_ws'] = null;
config.exclude_teams = [];
config.foreign_teams = [];
config.auto_play = true;
"""


def parse_reltime(s):
    """'1:23:45.678' 또는 '-0:00:10.000' 형식을 초(float)로."""
    if s is None:
        return None
    neg = s.startswith("-")
    h, m, sec = s.lstrip("-+").split(":")
    t = int(h) * 3600 + int(m) * 60 + float(sec)
    return -t if neg else t


class Api:
    def __init__(self, base, user, password):
        self.base = base.rstrip("/") + "/api/v4"
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Authorization": "Basic " + token, "Accept": "application/json",
                        "User-Agent": "spotboard-export/1.0"}

    def get(self, path):
        req = urllib.request.Request(self.base + path, headers=self.headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sys.exit("인증 실패(401): 아이디/비밀번호를 확인하세요.")
            if e.code == 403:
                sys.exit("권한 없음(403): 계정에 API reader 역할이 있는지 확인하세요.")
            if e.code == 404:
                sys.exit(f"찾을 수 없음(404): {path}  -- --cid 값을 /api/v4/contests 결과의 id로 지정했는지 확인하세요.")
            raise


def build(api, cid):
    contest = api.get(f"/contests/{cid}")
    problems = sorted(api.get(f"/contests/{cid}/problems"),
                      key=lambda p: (p.get("ordinal", 0), p.get("label", "")))
    teams = api.get(f"/contests/{cid}/teams")
    orgs = {o["id"]: o for o in api.get(f"/contests/{cid}/organizations")}
    groups = {g["id"]: g for g in api.get(f"/contests/{cid}/groups")}
    jtypes = {j["id"]: j for j in api.get(f"/contests/{cid}/judgement-types")}
    submissions = api.get(f"/contests/{cid}/submissions")
    judgements = api.get(f"/contests/{cid}/judgements")

    # 문제/팀 id -> Spotboard용 정수 id
    pmap, out_problems = {}, []
    for i, p in enumerate(problems):
        pmap[p["id"]] = i
        out_problems.append({
            "id": i,
            "name": p.get("label") or chr(ord("A") + i),
            "color": p.get("rgb") or p.get("color") or "white",
            "title": p.get("name", ""),
        })

    def hidden_team(t):
        if t.get("hidden"):
            return True
        gids = t.get("group_ids") or []
        return bool(gids) and all(groups.get(g, {}).get("hidden") for g in gids)

    tmap, out_teams = {}, []
    for t in sorted(teams, key=lambda t: str(t["id"])):
        if hidden_team(t):
            continue
        tid = len(out_teams) + 1
        tmap[t["id"]] = tid
        org = orgs.get(t.get("organization_id")) or {}
        out_teams.append({
            "id": tid,
            "name": t.get("display_name") or t.get("name") or str(t["id"]),
            "group": org.get("name") or "",
        })

    # 제출별 유효한(최신) 판정
    verdict = {}
    for j in sorted(judgements, key=lambda j: j.get("start_time") or ""):
        if j.get("valid", True) is False:
            continue
        verdict[j["submission_id"]] = j.get("judgement_type_id")

    runs, pending, skipped_ce = [], 0, 0
    duration = parse_reltime(contest["duration"])
    for s in sorted(submissions, key=lambda s: (parse_reltime(s["contest_time"]), str(s["id"]))):
        if s["team_id"] not in tmap or s["problem_id"] not in pmap:
            continue
        t = parse_reltime(s["contest_time"])
        if t < 0 or t >= duration:       # 대회 시간 밖 제출 제외
            continue
        jt = verdict.get(s["id"])
        if jt is None:
            result = ""                   # 채점 대기
            pending += 1
        else:
            info = jtypes.get(jt, {})
            if info.get("solved"):
                result = "Yes"
            elif info.get("penalty", True) is False:
                skipped_ce += 1           # 컴파일 에러 등 페널티 없는 판정은 제외
                continue
            else:
                result = "No - " + info.get("name", jt)
        runs.append({
            "id": len(runs) + 1,
            "team": tmap[s["team_id"]],
            "problem": pmap[s["problem_id"]],
            "result": result,
            "submissionTime": int(t // 60),
        })

    contest_json = {
        "title": contest.get("formal_name") or contest.get("name", ""),
        "systemName": "DOMjudge",
        "systemVersion": "",
        "problems": out_problems,
        "teams": out_teams,
    }
    runs_json = {
        "time": {"contestTime": int(duration), "noMoreUpdate": True, "timestamp": 0},
        "runs": runs,
    }
    freeze = contest.get("scoreboard_freeze_duration")
    # Spotboard는 submissionTime(분) <= time 인 제출을 공개하므로 프리즈 시작 1분 전까지로 설정
    freeze_min = int((duration - parse_reltime(freeze)) // 60) - 1 if freeze else None
    penalty = contest.get("penalty_time")
    return contest_json, runs_json, {
        "teams": len(out_teams), "problems": len(out_problems), "runs": len(runs),
        "pending": pending, "skipped_ce": skipped_ce, "freeze_min": freeze_min,
        "penalty": penalty,
    }


def install_webapp(webapp, out):
    if os.path.exists(os.path.join(out, "index.html")):
        return False
    if not webapp or not os.path.exists(os.path.join(webapp, "index.html")):
        sys.exit(f"{out}에 웹앱이 없습니다. --webapp 에 압축 푼 Spotboard 폴더(index.html 있는 곳)를 지정하세요.")
    shutil.copytree(webapp, out, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("sample"))
    return True


def patch_config(out):
    path = os.path.join(out, "config.js")
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if CONFIG_OVERRIDE_MARK not in src:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n" + CONFIG_OVERRIDE)


def write_json(path, data):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser(description="DOMJudge -> Spotboard 정적 스코어보드")
    ap.add_argument("--url", required=True, help="DOMJudge 주소 (예: http://1.2.3.4)")
    ap.add_argument("--cid", required=True, help="/api/v4/contests 에 나오는 콘테스트 id")
    ap.add_argument("--out", required=True, help="출력 폴더 (예: kgupc/2026/beginner)")
    ap.add_argument("--webapp", help="압축 푼 Spotboard 웹앱 폴더 (처음 한 번만 필요)")
    a = ap.parse_args()

    user = os.environ.get("DOMJUDGE_USER") or input("DOMJudge 아이디: ")
    password = os.environ.get("DOMJUDGE_PASS") or getpass.getpass("비밀번호: ")

    contest_json, runs_json, st = build(Api(a.url, user, password), a.cid)

    os.makedirs(a.out, exist_ok=True)
    if install_webapp(a.webapp, a.out):
        print(f"웹앱 복사: {a.webapp} -> {a.out}")
    patch_config(a.out)
    write_json(os.path.join(a.out, "contest.json"), contest_json)
    write_json(os.path.join(a.out, "runs.json"), runs_json)
    award = os.path.join(a.out, "award_slide.json")
    if not os.path.exists(award):
        write_json(award, [])

    print(f"완료: {a.out}")
    print(f"  팀 {st['teams']} / 문제 {st['problems']} / 제출 {st['runs']}"
          f" (채점 대기 {st['pending']}, 페널티 없는 판정 제외 {st['skipped_ce']})")
    if st["pending"]:
        print("  ! 채점 대기 제출이 있습니다. 채점이 끝난 뒤 다시 실행하세요.")
    if st["penalty"] not in (None, 20):
        print(f"  ! DOMJudge 페널티가 {st['penalty']}분입니다. Spotboard는 20분 고정이라 순위가 다를 수 있습니다.")
    if st["freeze_min"] is not None:
        print(f"  시상식 모드 주소: http://localhost:8000/?award=true&time={st['freeze_min']}")


if __name__ == "__main__":
    main()
