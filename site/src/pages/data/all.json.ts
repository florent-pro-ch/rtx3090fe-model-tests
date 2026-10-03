// /data/all.json — every record in one file, generated at build time.
import type { APIRoute } from 'astro';
import { allData } from '../../lib/data';

export const GET: APIRoute = () =>
  new Response(JSON.stringify(allData(), null, 1) + '\n', {
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
