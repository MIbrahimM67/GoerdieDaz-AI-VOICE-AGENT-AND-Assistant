/**
 * GeordieDaz — Session API calls
 */
import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '';

export async function getMySession(token) {
  const res = await axios.get(`${API_BASE}/session/me`, {
    headers: { Authorization: `Bearer ${token}` },
    withCredentials: true,
  });
  return res.data;
}
