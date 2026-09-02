import type { ApiClient } from "../api/client";
import { accessibleCompanies, completeActivation, login, logout, refresh, verifySession } from "../api/auth";
import { getCapabilities } from "../api/authorization";
import { ApiFailure } from "../api/types";
import type { Capability } from "../permissions/capabilities";
import type { SessionRepository } from "./sessionRepository";
import type { Session } from "./types";

export type EstablishedState = { kind: "authenticated"; capabilities: readonly Capability[]; identity: { displayName: string; login: string } } | { kind: "onboarding_incomplete" } | { kind: "access_limited" };

export class AuthenticationCoordinator {
  constructor(private readonly client: ApiClient, private readonly sessions: SessionRepository, private readonly qualifyEmployee: (capabilities: readonly Capability[]) => Promise<void>) {}

  async restore(): Promise<EstablishedState | { kind: "anonymous" }> {
    const stored = await this.sessions.load();
    if (!stored) return { kind: "anonymous" };
    try { return await this.establish(stored, true); }
    catch (error) {
      if (error instanceof ApiFailure && ["offline", "timeout", "unavailable"].includes(error.kind)) throw error;
      await this.sessions.clear(); this.client.clearTenantContext(); return { kind: "anonymous" };
    }
  }

  async signIn(email: string, password: string): Promise<EstablishedState> {
    this.client.clearTenantContext();
    const session = await login(this.client, email.trim(), password);
    await this.sessions.save(session);
    try { return await this.establish(session, true); }
    catch (error) {
      if (error instanceof ApiFailure && ["offline", "timeout", "unavailable"].includes(error.kind)) throw error;
      await this.sessions.clear(); this.client.clearTenantContext(); throw error;
    }
  }

  async signOut(): Promise<void> {
    try { await logout(this.client); } catch { /* Local revocation remains mandatory when server acknowledgement is unavailable. */ }
    await this.sessions.clear(); this.client.clearTenantContext();
  }

  activate(token: string, password: string) { this.client.clearTenantContext(); return completeActivation(this.client, token, password); }

  private async establish(session: Session, allowRefresh: boolean): Promise<EstablishedState> {
    this.client.clearTenantContext();
    let active = session;
    try { await verifySession(this.client); }
    catch (error) {
      if (!(error instanceof ApiFailure) || error.kind !== "unauthenticated" || !allowRefresh) throw error;
      active = await refresh(this.client, session.refresh_token);
      await this.sessions.save(active);
      await verifySession(this.client);
    }
    const companies = await accessibleCompanies(this.client);
    if (companies.length === 0) return { kind: "onboarding_incomplete" };
    if (companies.length !== 1) return { kind: "access_limited" };
    const company = companies[0]!;
    this.client.setTenantContext(company.id, company.default_branch_id);
    let capabilities: readonly Capability[];
    try { capabilities = await getCapabilities(this.client); }
    catch (error) {
      if (error instanceof ApiFailure && error.kind === "forbidden" && allowRefresh) {
        active = await refresh(this.client, active.refresh_token); await this.sessions.save(active); return this.establish(active, false);
      }
      throw error;
    }
    const usable = capabilities.some((value) => value === "time.self.view" || value === "my_day.view");
    if (!usable) return { kind: "access_limited" };
    try { await this.qualifyEmployee(capabilities); }
    catch (error) { if (error instanceof ApiFailure && error.kind === "not_ready") return { kind: "onboarding_incomplete" }; throw error; }
    return { kind: "authenticated", capabilities, identity: { displayName: active.user.display_name, login: active.user.normalized_email } };
  }
}
