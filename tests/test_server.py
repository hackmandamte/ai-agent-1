import os
import ssl
import unittest
import server

class ServerHelperTests(unittest.TestCase):
    def setUp(self):
        self.old_token=os.environ.get("AGENT_API_TOKEN"); os.environ["AGENT_API_TOKEN"]="test-token"
        with server._SESSIONS_LOCK: server._SESSIONS.clear()
    def tearDown(self):
        with server._SESSIONS_LOCK: server._SESSIONS.clear()
        if self.old_token is None: os.environ.pop("AGENT_API_TOKEN",None)
        else: os.environ["AGENT_API_TOKEN"]=self.old_token
    def test_token_required(self): self.assertEqual(server._token(),"test-token")
    def test_authorization_accepts_matching_bearer(self): self.assertTrue(server._authorized({"Authorization":"Bearer test-token"}))
    def test_authorization_rejects_missing_or_wrong_token(self):
        self.assertFalse(server._authorized({})); self.assertFalse(server._authorized({"Authorization":"Bearer wrong"}))
    def test_session_cookie_authorizes_and_refreshes(self):
        sid=server._create_session(); headers={"Cookie":f"agent_session={sid}"}; self.assertTrue(server._session_authorized(headers))
    def test_unknown_session_rejected(self): self.assertFalse(server._session_authorized({"Cookie":"agent_session=nope"}))
    def test_task_payload_is_sanitized(self):
        task=type("Task",(),{"task_id":"abc","goal":"inspect","status":"running","current_step":1,"max_steps":3,"verified":False,"last_error":None,"history":[{"tool":"system_info"}]})(); payload=server._task_payload(task); self.assertEqual(payload["task_id"],"abc"); self.assertNotIn("messages",payload); self.assertNotIn("result",payload)
    def test_client_routes_are_whitelisted(self): self.assertEqual(server._CLIENT_FILES["/"],"index.html"); self.assertEqual(server._CLIENT_FILES["/client/app.js"],"app.js"); self.assertNotIn("/client/../server.py",server._CLIENT_FILES)
    def test_client_assets_exist(self):
        for filename in server._CLIENT_FILES.values(): self.assertTrue((server._CLIENT_DIR/filename).is_file())
    def test_goal_limit_is_bounded(self): self.assertEqual(server.MAX_GOAL_LENGTH,12000)
    def test_concurrency_limit_is_bounded(self): self.assertEqual(server.MAX_CONCURRENT_TASKS,2)
    def test_session_ttl_is_bounded(self): self.assertEqual(server.SESSION_TTL_SECONDS,900)
    def test_non_loopback_requires_tls(self):
        with self.assertRaises(RuntimeError): server.serve(host="0.0.0.0",port=0)
    def test_tls_context_can_load(self): self.assertTrue(issubclass(ssl.SSLSocket,ssl.SSLSocket))

if __name__=="__main__": unittest.main()
