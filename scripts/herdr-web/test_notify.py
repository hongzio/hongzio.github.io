import json
import tempfile
import unittest
from unittest import mock

import config
import notify


class TestNormalize(unittest.TestCase):
    def test_empty_fills_defaults(self):
        conf = notify.normalize({})
        self.assertFalse(conf["options"]["include_password"])
        tg = conf["messengers"]["telegram"]
        self.assertFalse(tg["enabled"])
        self.assertEqual(tg["bot_token"], "")
        self.assertEqual(tg["chat_id"], "")

    def test_junk_is_coerced(self):
        conf = notify.normalize({"options": 5, "messengers": {"telegram": "nope"}})
        self.assertIn("telegram", conf["messengers"])
        self.assertFalse(conf["messengers"]["telegram"]["enabled"])

    def test_preserves_values(self):
        conf = notify.normalize({
            "options": {"include_password": True},
            "messengers": {"telegram": {"enabled": True, "bot_token": "t", "chat_id": "9"}},
        })
        self.assertTrue(conf["options"]["include_password"])
        self.assertEqual(conf["messengers"]["telegram"]["bot_token"], "t")


class TestRoundtrip(unittest.TestCase):
    def test_load_save(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(notify.load(d)["messengers"]["telegram"]["bot_token"], "")
            conf = notify.load(d)
            conf["messengers"]["telegram"].update(enabled=True, bot_token="abc", chat_id="42")
            notify.save(d, conf)
            got = notify.load(d)
            self.assertTrue(got["messengers"]["telegram"]["enabled"])
            self.assertEqual(got["messengers"]["telegram"]["chat_id"], "42")
            # persisted as real JSON on disk
            with open(config.notify_path(d)) as fh:
                self.assertEqual(json.load(fh)["messengers"]["telegram"]["bot_token"], "abc")


class TestRenderMessage(unittest.TestCase):
    def test_no_password_line_when_absent(self):
        msg = notify.render_message("https://x.trycloudflare.com", "herdr")
        self.assertIn("Public: https://x.trycloudflare.com", msg)
        self.assertIn("User: herdr", msg)
        self.assertNotIn("Password", msg)

    def test_password_line_when_present(self):
        msg = notify.render_message("https://x.trycloudflare.com", "herdr", "s3cr3t")
        self.assertIn("Password: s3cr3t", msg)


class TestSend(unittest.TestCase):
    def test_telegram_requires_fields(self):
        ok, err = notify.send("telegram", {"bot_token": "", "chat_id": ""}, "hi")
        self.assertFalse(ok)
        self.assertIn("required", err)

    def test_unknown_type(self):
        ok, err = notify.send("nope", {}, "hi")
        self.assertFalse(ok)

    def test_telegram_posts_expected_payload(self):
        with mock.patch.object(notify, "_post_json", return_value=b"{}") as post:
            ok, m = notify.send("telegram",
                                {"bot_token": "TOK", "chat_id": "42"}, "hello")
        self.assertTrue(ok)
        url, payload = post.call_args.args
        self.assertEqual(url, "https://api.telegram.org/botTOK/sendMessage")
        self.assertEqual(payload, {"chat_id": "42", "text": "hello"})

    def test_telegram_topic_adds_thread_id(self):
        with mock.patch.object(notify, "_post_json", return_value=b"{}") as post:
            ok, m = notify.send(
                "telegram",
                {"bot_token": "TOK", "chat_id": "42", "topic_id": "7"}, "hi")
        self.assertTrue(ok)
        self.assertEqual(post.call_args.args[1]["message_thread_id"], 7)  # int, not "7"

    def test_telegram_blank_topic_omitted(self):
        with mock.patch.object(notify, "_post_json", return_value=b"{}") as post:
            notify.send("telegram",
                        {"bot_token": "TOK", "chat_id": "42", "topic_id": ""}, "hi")
        self.assertNotIn("message_thread_id", post.call_args.args[1])

    def test_telegram_bad_topic_errors(self):
        with mock.patch.object(notify, "_post_json") as post:
            ok, err = notify.send(
                "telegram",
                {"bot_token": "TOK", "chat_id": "42", "topic_id": "x"}, "hi")
        self.assertFalse(ok)
        self.assertIn("number", err)
        post.assert_not_called()


class TestFetch(unittest.TestCase):
    def test_requires_token(self):
        ok, val, label = notify.fetch("telegram", {"bot_token": ""})
        self.assertFalse(ok)

    def test_picks_most_recent_chat(self):
        updates = {"result": [
            {"message": {"chat": {"id": 111, "first_name": "Old"}}},
            {"message": {"chat": {"id": 222, "title": "Group"}}},
        ]}
        with mock.patch.object(notify, "_get", return_value=json.dumps(updates).encode()):
            ok, result, label = notify.fetch("telegram", {"bot_token": "TOK"})
        self.assertTrue(ok)
        self.assertEqual(result, {"chat_id": "222"})  # no topic on a plain message
        self.assertEqual(label, "Group")

    def test_captures_topic_id_for_forum_message(self):
        updates = {"result": [
            {"message": {"chat": {"id": 222, "title": "Group"},
                         "message_thread_id": 9, "is_topic_message": True}},
        ]}
        with mock.patch.object(notify, "_get", return_value=json.dumps(updates).encode()):
            ok, result, label = notify.fetch("telegram", {"bot_token": "TOK"})
        self.assertTrue(ok)
        self.assertEqual(result, {"chat_id": "222", "topic_id": "9"})

    def test_ignores_thread_id_when_not_topic_message(self):
        # message_thread_id can appear on reply threads that aren't forum topics;
        # only capture it when is_topic_message marks a real topic.
        updates = {"result": [
            {"message": {"chat": {"id": 222, "title": "Group"},
                         "message_thread_id": 9}},
        ]}
        with mock.patch.object(notify, "_get", return_value=json.dumps(updates).encode()):
            ok, result, label = notify.fetch("telegram", {"bot_token": "TOK"})
        self.assertEqual(result, {"chat_id": "222"})

    def test_no_chats(self):
        with mock.patch.object(notify, "_get", return_value=b'{"result": []}'):
            ok, result, label = notify.fetch("telegram", {"bot_token": "TOK"})
        self.assertFalse(ok)
        self.assertIn("send a message", result)


class TestOnPublicUrl(unittest.TestCase):
    def test_sends_only_to_enabled(self):
        with tempfile.TemporaryDirectory() as d:
            config.load_settings(d)  # write default config.toml (username=herdr)
            conf = notify.load(d)
            conf["messengers"]["telegram"].update(
                enabled=True, bot_token="TOK", chat_id="42")
            notify.save(d, conf)
            with mock.patch.object(notify, "send",
                                   return_value=(True, "sent")) as send:
                results = notify.on_public_url("https://x.trycloudflare.com", d, d)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "telegram")
        self.assertNotIn("Password", send.call_args.args[2])  # toggle off by default
        self.assertEqual(results, [("telegram", True, "sent")])

    def test_skips_when_disabled(self):
        with tempfile.TemporaryDirectory() as d:
            config.load_settings(d)
            with mock.patch.object(notify, "send") as send:
                results = notify.on_public_url("https://x.trycloudflare.com", d, d)
        send.assert_not_called()
        self.assertEqual(results, [])

    def test_include_password_toggle(self):
        with tempfile.TemporaryDirectory() as d:
            config.load_settings(d)
            config.save_password(d, "topsecret")
            conf = notify.load(d)
            conf["options"]["include_password"] = True
            conf["messengers"]["telegram"].update(
                enabled=True, bot_token="TOK", chat_id="42")
            notify.save(d, conf)
            with mock.patch.object(notify, "send",
                                   return_value=(True, "sent")) as send:
                notify.on_public_url("https://x.trycloudflare.com", d, d)
        self.assertIn("Password: topsecret", send.call_args.args[2])

    def test_one_failure_does_not_block(self):
        with tempfile.TemporaryDirectory() as d:
            config.load_settings(d)
            conf = notify.load(d)
            conf["messengers"]["telegram"].update(
                enabled=True, bot_token="TOK", chat_id="42")
            notify.save(d, conf)
            with mock.patch.object(notify, "send", side_effect=RuntimeError("boom")):
                results = notify.on_public_url("https://x.trycloudflare.com", d, d)
        self.assertEqual(results[0][0], "telegram")
        self.assertFalse(results[0][1])


if __name__ == "__main__":
    unittest.main()
