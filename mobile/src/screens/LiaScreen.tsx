import { useEffect, useState } from "react";
import { AppState, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import type { LiaResponse, LiaService } from "../api/lia";
import { nativeSpeech, spokenTextForResponse, type SpeechAdapter } from "../lia/speech";
import { ApiFailure } from "../api/types";
import { colors, spacing, touchTarget } from "../design/tokens";
import { PrimaryButton } from "../components/PrimaryButton";
import { employeeActionDestination } from "../lia/actions";

type Message = { question: string; response: LiaResponse };
function failureMessage(error: unknown) {
  if (!(error instanceof ApiFailure)) return "LIA is temporarily unavailable. Please try again.";
  if (error.kind === "offline") return "You're offline. Connect to ask LIA.";
  if (error.kind === "unauthenticated") return "Your session has expired. Please sign in again.";
  if (error.kind === "forbidden") return "LIA is not available with your current Employee permissions.";
  if (error.kind === "malformed_response") return "LIA returned an unavailable response. Please retry.";
  return "LIA is temporarily unavailable. Please try again.";
}

function confidenceLabel(state: "CONFIDENT" | "CONFIRM_RECOMMENDED" | "UNCERTAIN", confirmed: boolean) {
  if (confirmed) return "Confirmed by the operator/customer";
  if (state === "CONFIDENT") return "Confident interpretation — still not canonical until confirmed";
  return "Low confidence — confirm this detail";
}

function ResponseCard({ item, speaking, onSpeak, onStop, onAction, onClarify, onTranslate }: { item: Message; speaking: boolean; onSpeak(): void; onStop(): void; onAction(action: NonNullable<LiaResponse["navigation"]>[number]): void; onClarify(prompt: string): void; onTranslate(prompt: string): void }) {
  const [expanded, setExpanded] = useState(false);
  const { response } = item;
  return <View style={styles.card}>
    <Text style={styles.question}>{item.question}</Text>
    <Text style={styles.answer}>{response.answer}</Text>
    <Text style={styles.meta}>{response.classification} · {response.response_mode} · {response.freshness.replaceAll("_", " ")}</Text>
    <Text style={styles.meta}>Evidence: {response.completeness.replaceAll("_", " ")}</Text>
    {response.safe_next_action && <Text style={styles.nextAction}>Next safe step: {response.safe_next_action}</Text>}
    {response.navigation.map((action, index) => { const destination = employeeActionDestination(action); return <View key={`${action.internal_path}-${index}`} style={styles.action}><Text style={styles.meta}>{action.available ? "Available action" : "Unavailable action"}: {action.label}</Text>{action.available && destination ? <PrimaryButton label={action.label} accessibilityLabel={`Open ${action.label}`} onPress={() => onAction(action)} /> : <Text style={styles.meta}>{action.unavailable_reason ?? "This action is not available in Employee Mobile."}</Text>}</View>; })}
    {response.csr_dispatch?.speech_interpretations.map((interpretation, index) => <View key={`${interpretation.owning_fact_type}-${interpretation.as_of}-${index}`} style={styles.clarification}>
      <Text style={styles.clarificationTitle}>{confidenceLabel(interpretation.state, interpretation.confirmed)}</Text>
      <Text style={styles.meta}>Heard: {interpretation.heard_text}</Text>
      {interpretation.possible_meaning && <Text style={styles.meta}>Possible meaning: {interpretation.possible_meaning}</Text>}
      <Text style={styles.meta}>Source language: {interpretation.source_language}{interpretation.interpreted_language ? ` · interpreted as ${interpretation.interpreted_language}` : ""}</Text>
      {interpretation.translation_state === "TRANSLATED" && <Text style={styles.meta}>Translation provenance: {interpretation.translation_provenance ?? "Server-provided translation"}</Text>}
      {interpretation.translation_state === "UNAVAILABLE" && <Text style={styles.meta}>Translation is unavailable for this detail.</Text>}
      <Text style={styles.meta}>As of {interpretation.as_of} · {interpretation.confirmed ? "confirmed" : "unconfirmed; not canonical"}</Text>
      {!interpretation.confirmed && <View style={styles.controls}><PrimaryButton label="Clarify" accessibilityLabel="Clarify this spoken detail" onPress={() => onClarify(interpretation.suggested_confirmation ?? `Please clarify this ${interpretation.owning_fact_type.replaceAll("_", " ")}.`)} />{interpretation.translation_state !== "TRANSLATED" && <PrimaryButton label="Translate" accessibilityLabel="Translate this spoken detail" onPress={() => onTranslate(`Translate this ${interpretation.owning_fact_type.replaceAll("_", " ")} from ${interpretation.source_language}.`)} />}</View>}
    </View>)}
    {response.as_of && <Text style={styles.meta}>As of {response.as_of}</Text>}
    <View style={styles.controls}>{speaking ? <PrimaryButton label="Stop" accessibilityLabel="Stop LIA playback" onPress={onStop} /> : <PrimaryButton label="Speak" accessibilityLabel="Speak this LIA answer" onPress={onSpeak} />}</View>
    <Pressable accessibilityRole="button" accessibilityLabel={expanded ? "Hide LIA evidence" : "Show LIA evidence"} accessibilityState={{ expanded }} onPress={() => setExpanded((value) => !value)} style={styles.evidenceButton}><Text style={styles.evidenceLabel}>{expanded ? "Hide supporting evidence" : "Show supporting evidence"}</Text></Pressable>
    {expanded && <View style={styles.evidence}>{response.evidence.map((evidence) => <View key={`${evidence.domain}-${evidence.evidence_digest}`}><Text style={styles.evidenceTitle}>{evidence.label}</Text><Text style={styles.meta}>Source: {evidence.authority} · {evidence.freshness.replaceAll("_", " ")}</Text>{evidence.limitations.map((limitation) => <Text key={limitation} style={styles.meta}>{limitation}</Text>)}</View>)}{response.limitations.map((limitation) => <Text key={limitation} style={styles.meta}>{limitation}</Text>)}</View>}
  </View>;
}

export function LiaScreen({ service, speech = nativeSpeech, onAction = () => undefined }: { service: LiaService; speech?: SpeechAdapter; onAction?: (action: NonNullable<LiaResponse["navigation"]>[number]) => void }) {
  const [question, setQuestion] = useState(""); const [messages, setMessages] = useState<Message[]>([]); const [conversationId, setConversationId] = useState<string>(); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null); const [speechError, setSpeechError] = useState<string | null>(null); const [speakingRequestId, setSpeakingRequestId] = useState<string | null>(null);
  useEffect(() => () => { speech.stop(); }, [speech]);
  useEffect(() => { const subscription = AppState.addEventListener("change", (state) => { if (state !== "active") { try { speech.stop(); } finally { setSpeakingRequestId(null); } } }); return () => subscription?.remove(); }, [speech]);
  const stop = () => { try { speech.stop(); } finally { setSpeakingRequestId(null); } };
  const submit = async () => { const value = question.trim(); if (!value || busy) return; stop(); setBusy(true); setError(null); try { const response = await service.ask(value, conversationId); setMessages((current) => [...current, { question: value, response }]); setConversationId(response.conversation_id); setQuestion(""); } catch (reason) { setError(failureMessage(reason)); } finally { setBusy(false); } };
  return <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === "ios" ? "padding" : undefined}><ScrollView style={styles.safe} contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled"><Text accessibilityRole="header" style={styles.title}>Ask LIA</Text><Text style={styles.intro}>Ask about your own assigned day and work. ACP Enterprise checks Employee permissions for every answer.</Text>{messages.length === 0 && <Text style={styles.empty}>Try “What is my next job?”</Text>}{messages.map((item, index) => <ResponseCard key={`${item.response.request_id}-${index}`} item={item} speaking={speakingRequestId === item.response.request_id} onSpeak={() => { stop(); setSpeechError(null); setSpeakingRequestId(item.response.request_id); try { speech.speak(spokenTextForResponse(item.response), { language: "en-US", rate: 0.94, pitch: 1 }); } catch { setSpeakingRequestId(null); setSpeechError("Spoken playback is unavailable on this device. You can still read the authorized answer."); } }} onStop={stop} onAction={onAction} onClarify={setQuestion} onTranslate={setQuestion} />)}{(error || speechError) && <View>{error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}{speechError && <Text accessibilityRole="alert" style={styles.error}>{speechError}</Text>}{error && <PrimaryButton label="Retry" disabled={busy || !question.trim()} onPress={() => void submit()} />}</View>}</ScrollView><View style={styles.composer}><TextInput accessibilityLabel="Ask LIA a question" placeholder="Ask about your assigned work" value={question} onChangeText={setQuestion} editable={!busy} multiline maxLength={1000} onSubmitEditing={() => void submit()} style={styles.input} /><PrimaryButton label={busy ? "Asking…" : "Send"} accessibilityLabel="Send question to Employee-safe LIA" disabled={busy || !question.trim()} onPress={() => void submit()} /></View></KeyboardAvoidingView>;
}

const styles = StyleSheet.create({ safe: { flex: 1, backgroundColor: colors.canvas }, body: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.lg }, title: { fontSize: 30, fontWeight: "800", color: colors.text }, intro: { fontSize: 16, lineHeight: 23, color: colors.muted }, empty: { color: colors.muted, fontStyle: "italic" }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 14, padding: spacing.md, gap: spacing.sm }, question: { fontWeight: "700", color: colors.muted }, answer: { fontSize: 18, lineHeight: 26, color: colors.text }, meta: { fontSize: 13, lineHeight: 19, color: colors.muted }, nextAction: { fontSize: 15, lineHeight: 21, color: colors.brand, fontWeight: "700" }, action: { gap: spacing.xs }, clarification: { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: spacing.sm, gap: spacing.xs }, clarificationTitle: { color: colors.warning, fontWeight: "800", fontSize: 14 }, controls: { flexDirection: "row", gap: spacing.sm }, evidenceButton: { minHeight: touchTarget, justifyContent: "center" }, evidenceLabel: { color: colors.brand, fontWeight: "700" }, evidence: { borderTopColor: colors.border, borderTopWidth: 1, paddingTop: spacing.sm, gap: spacing.xs }, evidenceTitle: { fontWeight: "700", color: colors.text }, error: { color: colors.danger, fontSize: 16, lineHeight: 22 }, composer: { borderTopColor: colors.border, borderTopWidth: 1, backgroundColor: colors.surface, padding: spacing.md, gap: spacing.sm }, input: { minHeight: touchTarget, maxHeight: 100, borderColor: colors.border, borderWidth: 1, borderRadius: 10, padding: spacing.sm, fontSize: 16, color: colors.text } });
