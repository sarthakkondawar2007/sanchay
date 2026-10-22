(() => {
  if (document.getElementById('sanchay-chat-launcher')) return;

  const css = document.createElement('link');
  css.rel = 'stylesheet';
  css.href = '/static/chatbot.css';
  document.head.appendChild(css);

  const launcher = document.createElement('button');
  launcher.id = 'sanchay-chat-launcher';
  launcher.type = 'button';
  launcher.title = 'Ask SANCHAY AI';
  launcher.setAttribute('aria-label', 'Open SANCHAY inventory assistant');
  launcher.textContent = '✦';

  const panel = document.createElement('section');
  panel.id = 'sanchay-chat';
  panel.setAttribute('aria-label', 'SANCHAY inventory assistant');
  panel.innerHTML = `
    <header><div><strong>SANCHAY AI Assistant</strong><small>Inventory help · Verified answers</small></div>
    <button id="sanchay-chat-close" type="button" aria-label="Close chat">×</button></header>
    <div id="sanchay-chat-messages" aria-live="polite"></div>
    <form id="sanchay-chat-form"><input id="sanchay-chat-input" maxlength="250" autocomplete="off" placeholder="Ask an inventory question…" aria-label="Your question" required><button type="submit">Send</button></form>
    <div id="sanchay-chat-hint">Answers use approved guidance and saved records. Unknown answers are not guessed.</div>`;

  document.body.append(launcher, panel);
  const messages = panel.querySelector('#sanchay-chat-messages');
  const form = panel.querySelector('#sanchay-chat-form');
  const input = panel.querySelector('#sanchay-chat-input');

  function addMessage(text, who) {
    const el = document.createElement('div');
    el.className = 'sc-message ' + (who === 'user' ? 'sc-user' : 'sc-bot');
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  launcher.addEventListener('click', () => {
    panel.classList.toggle('open');
    if (panel.classList.contains('open')) {
      if (!messages.children.length) addMessage('Hello! Ask me about inventory, stock, sales, purchases, suppliers, credits or reports.', 'bot');
      input.focus();
    }
  });
  panel.querySelector('#sanchay-chat-close').addEventListener('click', () => panel.classList.remove('open'));

  form.addEventListener('submit', async event => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    addMessage(question, 'user');
    input.value = '';
    input.disabled = true;
    form.querySelector('button').disabled = true;

    const pending = document.createElement('div');
    pending.className = 'sc-message sc-bot';
    pending.textContent = 'Checking approved answers and saved records…';
    messages.appendChild(pending);
    messages.scrollTop = messages.scrollHeight;

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        credentials: 'same-origin',
        body: JSON.stringify({message: question})
      });
      const data = await response.json();
      pending.remove();
      if (response.status === 401 || response.redirected) {
        addMessage('Please sign in again to use the assistant.', 'bot');
      } else if (response.ok && typeof data.answer === 'string') {
        addMessage(data.answer, 'bot');
      } else {
        addMessage("Sorry, I don't know.", 'bot');
      }
    } catch (_) {
      pending.remove();
      addMessage("Sorry, I don't know.", 'bot');
    } finally {
      input.disabled = false;
      form.querySelector('button').disabled = false;
      input.focus();
    }
  });
})();
