// Public backend address. Provider keys stay on Railway.
window.AGENT_API_BASE = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname) ? '' : 'https://positive-tranquility-production-9fdc.up.railway.app';
