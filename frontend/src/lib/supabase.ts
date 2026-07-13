// src/lib/supabase.ts
import { createClient } from '@supabase/supabase-js'

const rawUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || ''
const supabaseUrl = rawUrl.startsWith('http') ? rawUrl : 'https://dummy.supabase.co'
const supabaseKey  = process.env.NEXT_PUBLIC_SUPABASE_KEY  || 'dummy-key'

export const supabase = createClient(supabaseUrl, supabaseKey)
