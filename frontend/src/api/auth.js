/**
 * GeordieDaz — Auth API calls
 * All REST calls to /auth/* endpoints.
 */
import axios from 'axios';

const api = axios.create({
  baseURL: '/',
  withCredentials: true, // Include httpOnly cookies for refresh token
});

export async function register(username, email, password) {
  const res = await api.post('/auth/register', { username, email, password });
  return res.data;
}

export async function login(email, password) {
  const res = await api.post('/auth/login', { email, password });
  return res.data;
}

export async function getMe(token) {
  const res = await api.get('/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.data;
}

export async function refreshToken() {
  const res = await api.post('/auth/refresh');
  return res.data;
}

export async function logout(token) {
  await api.post('/auth/logout', null, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function fetchPersonas(token) {
  const res = await api.get('/personas', {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.data;
}
