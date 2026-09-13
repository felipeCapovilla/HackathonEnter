import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { documentDownloadUrl, sendJson } from "../api";
import { Icon } from "../Brand";
import { DOCUMENTOS } from "./textos";
import "./chat-documentos.css";

const suggestions = [
  ["Resumir os documentos", "Resuma os principais fatos dos documentos selecionados."],
  ["Conferir o crédito", "Há comprovante de liberação do crédito? Indique as fontes."],
  ["Ver pontos de atenção", "Quais pontos dos documentos selecionados precisam de conferência?"],
];

/** Acesso no topo do leitor; conversa e rascunho sobrevivem ao fechar o diálogo. */
export function ChatDocumentos({ caseId, caseNumber, documentos }) {
  const id = useId();
  const [conversationId, setConversationId] = useState(null);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null); // null = todos; [] = nenhum
  const [choosing, setChoosing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const dialog = useRef(null);
  const composer = useRef(null);
  const transcript = useRef(null);
  const expandButton = useRef(null);
  const sending = useRef(false);
  const available = documentos.filter((d) => ["COMPLETED", "COMPLETED_WITH_WARNINGS"].includes(d.status));
  const active = selected === null ? available : available.filter((d) => selected.includes(d.id));
  const canAsk = active.length > 0;
  const scope = selected === null ? `Todos os documentos · ${active.length}`
    : active.length === 1 ? DOCUMENTOS[active[0].declared_type] || active[0].original_filename
      : `${active.length} documentos selecionados`;

  useEffect(() => {
    if (!expanded) return undefined;
    const previousOverflow = document.body.style.overflow;
    const element = dialog.current;
    element.showModal();
    document.body.style.overflow = "hidden";
    composer.current?.focus({ preventScroll: true });
    return () => {
      element.close();
      document.body.style.overflow = previousOverflow;
      expandButton.current?.focus({ preventScroll: true });
    };
  }, [expanded]);

  useEffect(() => {
    const element = transcript.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [messages, pending, expanded]);

  useEffect(() => {
    const element = composer.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 132)}px`;
  }, [question, expanded]);

  const changeSelection = (next) => {
    setSelected(next);
    setConversationId(null);
    setError(null);
  };

  const ask = async (text = question, retryId = null) => {
    const asked = text.trim();
    if (!asked || sending.current || !canAsk) return;
    sending.current = true;
    setPending(true);
    setError(null);
    setChoosing(false);
    if (!retryId) setQuestion("");
    const messageId = retryId || crypto.randomUUID();
    if (!retryId) setMessages((old) => [...old, { id: messageId, role: "USER", content: asked, scope }]);
    try {
      let conversation = conversationId;
      if (!conversation) {
        const created = await sendJson(`/cases/${caseId}/document-chat/conversations`, {
          document_ids: selected === null ? [] : active.map((d) => d.id),
        });
        conversation = created.id;
        setConversationId(conversation);
      }
      const answer = await sendJson(`/cases/${caseId}/document-chat/conversations/${conversation}/messages`, { question: asked });
      setMessages((old) => [...old, answer]);
    } catch (e) {
      setError({ message: e.message, question: asked, messageId });
    } finally {
      sending.current = false;
      setPending(false);
    }
  };

  const content = <section className={`document-chat ${expanded ? "is-expanded" : ""}`} aria-labelledby={`${id}-title`}>
    <header className="dc-header">
      <span className="dc-mark"><Icon name="chat" /></span>
      <div className="dc-heading"><h3 id={`${id}-title`}>Converse com os documentos</h3>
        <p>{caseNumber ? `Processo ${caseNumber}` : "Perguntas e respostas com fontes"}</p></div>
      <div className="dc-actions">
        {messages.length > 0 && <button type="button" className="dc-icon-button" title="Nova conversa" aria-label="Nova conversa" disabled={pending}
          onClick={() => { setMessages([]); setConversationId(null); setError(null); composer.current?.focus(); }}><Icon name="plus" /></button>}
        <button type="button" className="dc-icon-button" title="Voltar aos documentos (Esc)" aria-label="Fechar chat"
          onClick={() => setExpanded(false)}><Icon name="close" /></button>
      </div>
    </header>

    <div className="dc-sources">
      <div className="dc-source-bar"><span className="dc-scope"><Icon name="files" /><span>{scope}</span></span>
        <button type="button" className="dc-text-button" disabled={pending || !available.length} aria-expanded={choosing}
          aria-controls={`${id}-sources`} onClick={() => setChoosing((value) => !value)}>
          {choosing ? "Concluir" : "Selecionar"}<Icon name={choosing ? "check" : "chevronDown"} /></button></div>
      {!choosing && selected !== null && active.length > 0 && <div className="dc-selected-tags" aria-label="Documentos selecionados">
        {active.slice(0, 3).map((d) => <span key={d.id} title={d.original_filename}>{d.original_filename}</span>)}
        {active.length > 3 && <span>+{active.length - 3}</span>}
      </div>}
      {choosing && <fieldset className="dc-source-picker" id={`${id}-sources`} disabled={pending}>
        <legend className="dc-sr-only">Escolha os documentos da consulta</legend>
        <label className={`dc-source-option dc-source-all ${selected === null ? "is-selected" : ""}`}>
          <input type="checkbox" checked={selected === null} onChange={(e) => changeSelection(e.target.checked ? null : [])} />
          <span><strong>Todos os documentos</strong><small>Consultar os {available.length} arquivos disponíveis</small></span>
        </label>
        {available.map((d) => <label key={d.id} className={`dc-source-option ${active.some((item) => item.id === d.id) ? "is-selected" : ""}`}>
          <input type="checkbox" checked={active.some((item) => item.id === d.id)} onChange={() => {
            const ids = active.map((item) => item.id);
            changeSelection(ids.includes(d.id) ? ids.filter((value) => value !== d.id) : [...ids, d.id]);
          }} />
          <span><strong>{DOCUMENTOS[d.declared_type] || "Documento"}<small>{d.page_count} pág.</small></strong>
            <small title={d.original_filename}>{d.original_filename}</small></span>
        </label>)}
        {messages.length > 0 && <p className="dc-selection-note">A seleção vale para as próximas perguntas. As mensagens anteriores continuam abaixo.</p>}
      </fieldset>}
    </div>

    <div ref={transcript} className="dc-transcript" role="log" aria-label="Conversa sobre os documentos" aria-live="polite" tabIndex={0}>
      {messages.length === 0 && <div className="dc-empty">
        <span className="dc-empty-icon"><Icon name="spark" /></span>
        <h4>{available.length ? "O que você quer entender?" : "Os documentos chegam primeiro"}</h4>
        <p>{available.length ? "Explore os fatos, confira valores e encontre as fontes nos documentos do processo." : "Assim que um documento terminar de processar, você poderá fazer sua primeira pergunta."}</p>
        {available.length > 0 && <div className="dc-suggestions">{suggestions.map(([label, text]) => <button type="button" key={label}
          disabled={!canAsk} onClick={() => { setQuestion(text); composer.current?.focus(); }}><Icon name="arrow" />{label}</button>)}</div>}
      </div>}
      {messages.map((message) => <div key={message.id} className={`dc-message ${message.role === "USER" ? "is-user" : "is-assistant"}`}>
        <div className="dc-message-label">{message.role === "USER" ? "Você" : <><Icon name="spark" />Assistente documental</>}</div>
        <div className="dc-bubble"><p>{message.content}</p>
          {message.citations?.length > 0 && <div className="dc-references"><span>Fontes da resposta</span><div className="dc-citation-links">
            {message.citations.map((citation, index) => <a key={`${citation.chunk_id}-${index}`} target="_blank" rel="noopener noreferrer"
              title={`${citation.filename} — ${citation.quote || "Conferir fonte"}`}
              href={`${documentDownloadUrl(citation.document_id)}?inline=1#page=${citation.page_start}`}>
              <span className="dc-citation-index">{index + 1}</span><span className="dc-citation-name">{citation.filename}</span>
              <span className="dc-citation-page">p. {citation.page_start}{citation.page_end !== citation.page_start ? `–${citation.page_end}` : ""}</span><Icon name="external" /></a>)}
          </div></div>}
        </div>
        {message.scope && <small className="dc-message-scope">{message.scope}</small>}
      </div>)}
      {pending && <div className="dc-working" role="status"><span className="dc-typing" aria-hidden="true"><i /><i /><i /></span>Consultando os documentos…</div>}
      {error && <div className="dc-error" role="alert"><p>{error.message}</p><button type="button" className="dc-text-button" disabled={pending || !canAsk}
        onClick={() => ask(error.question, error.messageId)}>Tentar novamente<Icon name="arrow" /></button></div>}
    </div>

    <footer className="dc-footer">
      {!canAsk && available.length > 0 && <p className="dc-selection-note" role="status">Selecione ao menos um documento para perguntar.</p>}
      <form className="dc-composer" onSubmit={(event) => { event.preventDefault(); ask(); }}>
        <label htmlFor={`${id}-question`} className="dc-sr-only">Pergunta sobre os documentos</label>
        <textarea ref={composer} id={`${id}-question`} value={question} onChange={(event) => setQuestion(event.target.value)} rows={1} maxLength={2000}
          placeholder="Pergunte sobre os documentos…" disabled={!canAsk} onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); ask(); }
          }} />
        <button type="submit" className="dc-send" title="Enviar pergunta" aria-label="Enviar pergunta" disabled={pending || !canAsk || !question.trim()}><Icon name="send" /></button>
      </form>
      <div className="dc-composer-hint"><span>Confira as fontes antes de decidir.</span><span className="dc-keyboard-hint">Enter envia · Shift + Enter quebra linha</span>
        {question.length > 1800 && <span>{question.length}/2000</span>}</div>
    </footer>
  </section>;

  return <>
    <div className="dc-launcher">
      <span className="dc-mark"><Icon name="spark" /></span>
      <div className="dc-launcher-copy"><strong>Entenda os documentos com IA</strong>
        <span>{pending ? "Consultando os documentos…" : messages.length > 0 ? "Sua conversa está aqui. Continue de onde parou." : "Tire dúvidas e confira as fontes, sem sair do processo."}</span></div>
      <button ref={expandButton} type="button" className="dc-launch-button" aria-haspopup="dialog" onClick={() => setExpanded(true)}>
        <Icon name="chat" />{messages.length > 0 ? "Continuar conversa" : "Perguntar à IA"}<Icon name="expand" /></button>
    </div>
    {expanded && createPortal(<dialog ref={dialog} className="dc-dialog" aria-labelledby={`${id}-title`}
      onCancel={(event) => { event.preventDefault(); setExpanded(false); }}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), [tabindex="0"]')]
          .filter((element) => element.getClientRects().length > 0);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }}
      onClick={(event) => { if (event.target === event.currentTarget) setExpanded(false); }}>{content}</dialog>, document.body)}
  </>;
}
