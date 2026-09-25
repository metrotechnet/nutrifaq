const API_BASE = (window.API_BASE || "http://localhost:8080").trim();
const CLIENT_QUERY_KEY = (window.CLIENT_QUERY_KEY || "").trim();

const display = document.getElementById("display");
const form = document.getElementById("composer");
const input = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");
const downloadBtn = document.getElementById("downloadBtn");
const fileInput = document.getElementById("fileInput");

if (typeof marked !== "undefined") {
  const renderer = new marked.Renderer();
  const baseLinkRenderer = renderer.link;
  renderer.link = (href, title, text) => {
    const html = baseLinkRenderer.call(renderer, href, title, text);
    return html.replace("<a ", '<a target="_blank" rel="noopener noreferrer" ');
  };
  marked.setOptions({ renderer });
}

// Purpose: Implements a focused frontend behavior used by this module.
// Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
function sanitizeMarkdown(mdText) {
  const rendered = typeof marked !== "undefined" ? marked.parse(mdText) : mdText;
  if (typeof DOMPurify !== "undefined") {
    return DOMPurify.sanitize(rendered);
  }
  return rendered;
}

// Purpose: Implements a focused frontend behavior used by this module.
// Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
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

// Purpose: Fetches and prepares data needed by the UI flow that calls this function.
// Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
function loadingDotsMarkup() {
  return `
    <div class="loading" aria-label="Generation en cours" role="status">
      <span class="loading-dot"></span>
      <span class="loading-dot"></span>
      <span class="loading-dot"></span>
    </div>
  `;
}

// Purpose: Updates UI or local state so downstream interactions stay consistent.
// Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
function setLoading(isLoading) {
  input.disabled = isLoading;
  sendBtn.disabled = isLoading;
  downloadBtn.disabled = isLoading;
}

// Purpose: Implements a focused frontend behavior used by this module.
// Inputs/Outputs: Uses the function parameters and returns the value expected by its callers.
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

  if (CLIENT_QUERY_KEY) {
    headers["X-Client-Key"] = CLIENT_QUERY_KEY;
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

async function uploadSelectedFile(file) {
  const headers = {
  };

  if (CLIENT_QUERY_KEY) {
    headers["X-Client-Key"] = CLIENT_QUERY_KEY;
  }

  const formData = new FormData();
  formData.append("file", file, file.name);

  const response = await fetch(`${API_BASE}/download_page`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`HTTP ${response.status}: ${body || "Echec du transfert"}`);
  }

  return response.json();
}

async function uploadSelectedFiles(files) {
  const summary = [];

  for (const file of files) {
    try {
      const result = await uploadSelectedFile(file);
      summary.push({
        ok: true,
        fileName: file.name,
        result,
      });
    } catch (error) {
      summary.push({
        ok: false,
        fileName: file.name,
        error,
      });
    }
  }

  return summary;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) {
    return;
  }

  addBubble("user", question);
  const assistantBubble = addBubble("assistant", "");
  assistantBubble.innerHTML = loadingDotsMarkup();
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

downloadBtn.addEventListener("click", () => {
  fileInput.value = "";
  fileInput.click();
});

fileInput.addEventListener("change", async () => {
  const files = Array.from(fileInput.files || []);
  if (files.length === 0) {
    return;
  }

  const userMessage = files.length === 1
    ? `Téléchargement du fichier: ${files[0].name}`
    : `Téléchargement en lot: ${files.length} fichiers (${files.map((file) => file.name).join(", ")})`;
  addBubble("user", userMessage);
  const assistantBubble = addBubble("assistant", "");
  assistantBubble.innerHTML = loadingDotsMarkup();
  setLoading(true);

  try {
    const results = await uploadSelectedFiles(files);
    const successResults = results.filter((item) => item.ok);
    const failureResults = results.filter((item) => !item.ok);

    const lines = [];
    lines.push(`Transfert terminé: ${successResults.length}/${results.length} fichier(s) envoyé(s) avec succès.`);

    if (successResults.length > 0) {
      lines.push("");
      lines.push("Fichiers transférés:");
      for (const item of successResults) {
        lines.push(`- ${item.fileName} → ${item.result.filename}`);
      }
    }

    if (failureResults.length > 0) {
      lines.push("");
      lines.push("Fichiers en erreur:");
      for (const item of failureResults) {
        lines.push(`- ${item.fileName}: ${item.error.message}`);
      }
    }

    assistantBubble.innerHTML = sanitizeMarkdown(lines.join("\n"));
  } catch (error) {
    assistantBubble.innerHTML = `<span class="error">${error.message}</span>`;
  } finally {
    setLoading(false);
    input.focus();
    display.scrollTop = display.scrollHeight;
  }
});
