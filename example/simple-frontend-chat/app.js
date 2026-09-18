const API_BASE = "https://nutrifaq-webapp.azurewebsites.net";
const CLIENT_BEARER_TOKEN = (window.CLIENT_BEARER_TOKEN || "").trim();

const display = document.getElementById("display");
const form = document.getElementById("composer");
const input = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");

if (typeof marked !== "undefined") {
  const renderer = new marked.Renderer();
  const baseLinkRenderer = renderer.link;
  renderer.link = (href, title, text) => {
    const html = baseLinkRenderer.call(renderer, href, title, text);
    return html.replace("<a ", '<a target="_blank" rel="noopener noreferrer" ');
  };
  marked.setOptions({ renderer });
}

function sanitizeMarkdown(mdText) {
  const rendered = typeof marked !== "undefined" ? marked.parse(mdText) : mdText;
  if (typeof DOMPurify !== "undefined") {
    return DOMPurify.sanitize(rendered);
  }
  return rendered;
}

function addBubble(role, initialText = "") {
  const row = document.createElement("div");
  row.className = `row ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble markdown";

  if (role === "user") {
    bubble.textContent = initialText;
  } else {
    bubble.innerHTML = sanitizeMarkdown(initialText);
  }

  row.appendChild(bubble);
  display.appendChild(row);
  display.scrollTop = display.scrollHeight;
  return bubble;
}

function setLoading(isLoading) {
  input.disabled = isLoading;
  sendBtn.disabled = isLoading;
}

function parseSseEvent(rawEvent) {
  const lines = rawEvent.split("\n");
  const dataLines = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());
  return dataLines.join("\n");
}

async function streamQuery(question, assistantBubble) {
  const headers = {
    "Content-Type": "application/json",
  };
  if (CLIENT_BEARER_TOKEN) {
    headers.Authorization = `Bearer ${CLIENT_BEARER_TOKEN}`;
  }

  const response = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      question,
      language: "fr",
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`HTTP ${response.status}: ${body || "Echec de la requete"}`);
  }

  if (!response.body) {
    throw new Error("Aucun flux de reponse disponible.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let fullText = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });

    let boundaryIndex = buffer.indexOf("\n\n");
    while (boundaryIndex !== -1) {
      const eventChunk = buffer.slice(0, boundaryIndex);
      buffer = buffer.slice(boundaryIndex + 2);

      const data = parseSseEvent(eventChunk);
      if (!data) {
        boundaryIndex = buffer.indexOf("\n\n");
        continue;
      }

      if (data === "[DONE]") {
        return;
      }

      try {
        const payload = JSON.parse(data);
        if (payload.chunk) {
          fullText += payload.chunk;
          assistantBubble.innerHTML = sanitizeMarkdown(fullText);
          display.scrollTop = display.scrollHeight;
        }
        if (payload.error) {
          throw new Error(payload.error);
        }
      } catch (err) {
        if (err instanceof SyntaxError) {
          fullText += data;
          assistantBubble.innerHTML = sanitizeMarkdown(fullText);
        } else {
          throw err;
        }
      }

      boundaryIndex = buffer.indexOf("\n\n");
    }
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) {
    return;
  }

  addBubble("user", question);
  const assistantBubble = addBubble("assistant", "Generation de la reponse...");
  input.value = "";
  setLoading(true);

  try {
    await streamQuery(question, assistantBubble);
  } catch (error) {
    assistantBubble.innerHTML = `<span class="error">${error.message}</span>`;
  } finally {
    setLoading(false);
    input.focus();
    display.scrollTop = display.scrollHeight;
  }
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
