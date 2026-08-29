import type { ProtectedStorage } from "../storage/secureStorage";
import type { Session } from "./types";

const SESSION_KEY = "acp.employee.session.v1";

export class SessionRepository {
  constructor(private readonly storage: ProtectedStorage) {}
  async load(): Promise<Session | null> {
    const raw = await this.storage.get(SESSION_KEY);
    if (!raw) return null;
    try {
      const session = JSON.parse(raw) as Session;
      if (!session.access_token || !session.refresh_token) throw new Error("invalid session");
      return session;
    } catch {
      await this.clear();
      return null;
    }
  }
  save(session: Session): Promise<void> { return this.storage.set(SESSION_KEY, JSON.stringify(session)); }
  clear(): Promise<void> { return this.storage.remove(SESSION_KEY); }
}
