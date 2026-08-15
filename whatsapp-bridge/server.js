const http = require("http");
const axios = require("axios");
const qrcode = require("qrcode-terminal");
const { Client, LocalAuth } = require("whatsapp-web.js");

const PORT = Number(process.env.PORT || "4545");
const JARVIS_BACKEND_URL = (process.env.JARVIS_BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 2_000_000) {
        reject(new Error("Request too large"));
      }
    });
    req.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {});
      } catch (err) {
        reject(err);
      }
    });
  });
}

function normalizeRecipient(to) {
  const cleaned = String(to || "").trim();
  if (!cleaned) return "";
  if (cleaned.includes("@")) return cleaned;
  const digits = cleaned.replace(/[^\d]/g, "");
  if (!digits) return cleaned;
  return `${digits}@c.us`;
}

const client = new Client({
  authStrategy: new LocalAuth({ clientId: "jarvis" })
});

client.on("qr", (qr) => {
  qrcode.generate(qr, { small: true });
});

client.on("ready", () => {
  console.log("WhatsApp bridge ready");
});

client.on("message", async (msg) => {
  const payload = {
    sender: msg.from,
    message: msg.body
  };
  try {
    await axios.post(`${JARVIS_BACKEND_URL}/api/incoming-whatsapp`, payload, { timeout: 20_000 });
  } catch (err) {
    const detail = err?.response?.data || err?.message || String(err);
    console.error("Failed to notify Jarvis backend:", detail);
  }
});

client.initialize();

const server = http.createServer(async (req, res) => {
  if (req.method === "POST" && req.url === "/send-message") {
    try {
      const body = await readJson(req);
      const to = normalizeRecipient(body.to);
      const message = String(body.message || "").trim();
      if (!to || !message) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: false, error: "to and message are required" }));
        return;
      }
      await client.sendMessage(to, message);
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: true }));
      return;
    } catch (err) {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ ok: false, error: err?.message || String(err) }));
      return;
    }
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ ok: false, error: "Not found" }));
});

server.listen(PORT, () => {
  console.log(`WhatsApp bridge listening on port ${PORT}`);
});

