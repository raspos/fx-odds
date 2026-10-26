"""하루 1회 정규 배치: 수집 -> 분석 -> 정적 JSON. 수집이 실패해도 이전 정상 데이터로 빌드하며 meta.json 의 stale_warning 으로 알린다."""
import json, sys, traceback
from datetime import datetime, timezone
import fetch, build
from common import DATA, redact


def main() -> int:
    status = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        status.update(fetch.run())
    except Exception as e:  # 네트워크 전면 실패 -> 이전 DB 유지
        status["fatal"] = redact(repr(e))[:200]
        traceback.print_exc()
    (DATA / "fetch_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    build.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
