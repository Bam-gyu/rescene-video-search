import sys
import unicodedata
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import update as u

NOW = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)


def video(views, is_short=False, channel="UCother", published="2026-10-01T00:00:00Z", title="RESCENE 무대"):
    return {"title": title, "channelId": channel, "channelTitle": "채널", "publishedAt": published,
            "views": views, "thumbnail": "", "isShort": is_short}


class PureFunctions(unittest.TestCase):
    def test_parse_duration(self):
        self.assertEqual(u.parse_duration("PT1H2M3S"), 3723)
        self.assertEqual(u.parse_duration("PT45S"), 45)
        self.assertEqual(u.parse_duration("PT3M"), 180)
        self.assertEqual(u.parse_duration("P0D"), 0)
        self.assertEqual(u.parse_duration(None), 0)

    def test_mentions_rescene(self):
        self.assertTrue(u.mentions_rescene("[MV] Rescene - Love Attack"))
        self.assertTrue(u.mentions_rescene("", "#리센느 #원이"))
        self.assertFalse(u.mentions_rescene("다른 그룹 무대", None))

    def test_fan_channel(self):
        fan = ["리센느 원이 직캠"] * 15 + ["일상 브이로그"] * 5
        broadcaster = ["RESCENE 무대"] * 3 + ["다른 가수 무대"] * 17
        self.assertTrue(u.is_fan_channel("UCfan", fan))
        self.assertFalse(u.is_fan_channel("UCkbs", broadcaster))
        self.assertFalse(u.is_fan_channel("UCtKtCiaWRz-d3EZn2xd1mdA", fan))  # 공식 채널은 예외
        self.assertFalse(u.is_fan_channel("UCempty", []))
        self.assertFalse(u.is_fan_channel("UCbig", fan, subscribers=194_000))  # 방송사 프로그램 채널
        self.assertTrue(u.is_fan_channel("UCfan", fan, subscribers=50_000))

    def test_is_short_video(self):
        self.assertTrue(u.is_short_video(45, 270, 480))  # 세로
        self.assertTrue(u.is_short_video(170, 480, 480))  # 정사각형, 3분 이내
        self.assertFalse(u.is_short_video(45, 480, 270))  # 가로
        self.assertFalse(u.is_short_video(200, 270, 480))  # 3분 초과 세로
        self.assertFalse(u.is_short_video(30, 0, 0))  # 정보 없음

    def test_is_foreign(self):
        def v(title, lang="", channel="UCx"):
            return {"title": title, "lang": lang, "channelId": channel}
        self.assertTrue(u.is_foreign(v("【RESCENE】20kg減量したミナミ")))  # 일본어
        self.assertTrue(u.is_foreign(v("【RESCENE中字】大阪之旅真崩潰")))  # 중국어
        self.assertTrue(u.is_foreign(v("ELA TEM 34 ANOS E PARECE PARTE DO RESCENE!!", lang="pt-BR")))
        self.assertFalse(u.is_foreign(v("[K-POP] RESCENE Eats Like Family!", lang="ko")))  # 영어 제목, 한국어 음성
        self.assertFalse(u.is_foreign(v("[K-POP] RESCENE Reveal Their Dorm", lang="en")))  # MBC WORLD 같은 글로벌 채널
        self.assertFalse(u.is_foreign(v("RESCENE - LOVE ATTACK")))  # 언어 정보 없으면 유지
        self.assertFalse(u.is_foreign(v(unicodedata.normalize("NFD", "폭로전이 된 RESCENE"))))  # 자모 분리된 한글
        self.assertFalse(u.is_foreign(v("リセンヌ 日本デビュー", channel="UCtKtCiaWRz-d3EZn2xd1mdA")))  # 공식 채널

    def test_parse_blocklist(self):
        text = "# 주석\nUCaaa  # 팬채널\n\n UCbbb \n"
        self.assertEqual(u.parse_blocklist(text), {"UCaaa", "UCbbb"})

    def test_thresholds(self):
        self.assertTrue(u.passes_threshold(video(50_000)))
        self.assertFalse(u.passes_threshold(video(49_999)))
        self.assertFalse(u.passes_threshold(video(99_999, is_short=True)))
        self.assertTrue(u.passes_threshold(video(100_000, is_short=True)))

    def test_prune_keeps_passing_and_recent(self):
        videos = {
            "old_low": video(1_000, published="2025-01-01T00:00:00Z"),
            "old_high": video(60_000, published="2025-01-01T00:00:00Z"),
            "new_low": video(1_000, published="2026-10-10T00:00:00Z"),
        }
        self.assertEqual(set(u.prune(videos, NOW)), {"old_high", "new_low"})


class BuildOutput(unittest.TestCase):
    def test_split_filter_and_sort(self):
        videos = {
            "long_old": video(70_000, published="2026-01-01T00:00:00Z"),
            "long_new": video(70_000, published="2026-09-01T00:00:00Z"),
            "long_low": video(10_000),
            "long_fan": video(900_000, channel="UCfan"),
            "short_fan": video(200_000, is_short=True, channel="UCfan"),
            "short_low": video(90_000, is_short=True),
            "blocked": video(900_000, channel="UCblocked"),
            "foreign": video(900_000, title="RESCENEの日本人メンバー"),
        }
        channels = {"UCfan": {"fan": True}}
        out = u.build_output(videos, channels, {"UCblocked"}, NOW)
        self.assertEqual([v["id"] for v in out["long"]], ["long_new", "long_old"])
        self.assertEqual([v["id"] for v in out["shorts"]], ["short_fan"])  # 쇼츠는 팬 채널도 허용
        self.assertEqual(out["updatedAt"], "2026-10-13T10:00:00Z")
        self.assertNotIn("isShort", out["long"][0])


if __name__ == "__main__":
    unittest.main()
