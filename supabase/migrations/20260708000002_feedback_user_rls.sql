-- Feedback-as-signal: let a signed-in user READ their own feedback so the
-- frontend can fold past 👍/👎 into personalized recommendations. Writes still
-- go through the backend (/api/feedback, service_role) — this adds read-only
-- access to a user's own rows. user_id is TEXT holding the auth uid string.
CREATE POLICY "users read own feedback" ON feedback
  FOR SELECT TO authenticated
  USING (user_id = auth.uid()::text);

GRANT SELECT ON feedback TO authenticated;
