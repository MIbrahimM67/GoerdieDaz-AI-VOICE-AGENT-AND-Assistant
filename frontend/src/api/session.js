/**
 * GeordieDaz — Session API calls
 */
import axios from 'axios';

export async function getMySession(token) {
  const res = await axios.get('/session/me', {
    headers: { Authorization: `Bearer ${token}` },
    withCredentials: true,
  });
  return res.data;
}
