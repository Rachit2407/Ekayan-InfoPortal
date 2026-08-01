// js/config.js
// Supabase Project URL and Anon API Key (reused from Ekayan Bridge configuration)
const supabaseUrl = 'https://xzbnlvqeesxwtidsupvy.supabase.co';
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inh6Ym5sdnFlZXN4d3RpZHN1cHZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODU1NzUzODIsImV4cCI6MjEwMTE1MTM4Mn0.mU1iW3l66zb7eixpf4KqwEntCcyG90MnFNzmW74oeO4';

// Set to true when you want to switch from LocalStorage to Supabase cloud database
const USE_SUPABASE = true;

// Safe initialization that won't throw if script tag is missing
const supabaseClient = (USE_SUPABASE && supabaseUrl && supabaseKey && window.supabase) 
  ? window.supabase.createClient(supabaseUrl, supabaseKey) 
  : null;

window.USE_SUPABASE = USE_SUPABASE;
window.supabaseClient = supabaseClient;
