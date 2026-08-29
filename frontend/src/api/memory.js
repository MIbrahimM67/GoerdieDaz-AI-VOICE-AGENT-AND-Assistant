/**
 * GeordieDaz — Memory API calls
 * All REST calls to /core/* endpoints.
 */
import axios from 'axios';

const api = axios.create({
  baseURL: '/',
  withCredentials: true,
});

export async function fetchCoreFacts(token) {
  const res = await api.get('/core', {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.data;
}

export async function addCoreFact(token, content) {
  const res = await api.post(
    '/core',
    { content },
    {
      headers: { Authorization: `Bearer ${token}` },
    }
  );
  return res.data;
}
