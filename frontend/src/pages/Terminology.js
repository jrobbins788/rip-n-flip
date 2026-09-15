import { useState, useEffect } from 'react';
import Navbar from '../components/Navbar';
import { Input } from '@/components/ui/input';
import { Search, BookOpen, Info } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Terminology() {
  const [terms, setTerms] = useState([]);
  const [filteredTerms, setFilteredTerms] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTerms();
  }, []);

  useEffect(() => {
    if (search) {
      const filtered = terms.filter(
        (term) =>
          term.term.toLowerCase().includes(search.toLowerCase()) ||
          term.meaning.toLowerCase().includes(search.toLowerCase())
      );
      setFilteredTerms(filtered);
    } else {
      setFilteredTerms(terms);
    }
  }, [search, terms]);

  const fetchTerms = async () => {
    try {
      const response = await fetch(`${API}/knowledge/terminology`);
      const data = await response.json();
      setTerms(data);
      setFilteredTerms(data);
    } catch (error) {
      console.error('Error fetching terminology:', error);
    } finally {
      setLoading(false);
    }
  };

  // Group terms by first letter
  const groupedTerms = filteredTerms.reduce((acc, term) => {
    const firstChar = term.term.charAt(0).toUpperCase();
    // Check if starts with number or symbol
    const key = /^[A-Z]/.test(firstChar) ? firstChar : '#';
    if (!acc[key]) {
      acc[key] = [];
    }
    acc[key].push(term);
    return acc;
  }, {});

  const sortedKeys = Object.keys(groupedTerms).sort((a, b) => {
    if (a === '#') return -1;
    if (b === '#') return 1;
    return a.localeCompare(b);
  });

  if (loading) {
    return (
      <div className="min-h-screen bg-[#050505]">
        <Navbar />
        <div className="pt-24 flex items-center justify-center">
          <div className="text-[#00F0FF] font-mono animate-pulse">LOADING TERMINOLOGY...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#050505] noise-bg">
      <Navbar />
      
      <main className="pt-24 pb-12 px-4">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="mb-12">
            <div className="inline-flex items-center gap-2 bg-[#FF0099]/10 border border-[#FF0099]/30 px-4 py-2 mb-4">
              <BookOpen className="w-4 h-4 text-[#FF0099]" />
              <span className="text-[#FF0099] font-mono text-sm">CARD COLLECTOR'S DICTIONARY</span>
            </div>
            <h1 className="font-heading text-5xl sm:text-6xl font-bold text-white uppercase tracking-tight">
              TERMINOLOGY <span className="text-[#FF0099]">LEGEND</span>
            </h1>
            <p className="text-white/50 mt-2">Master the language of card collecting</p>
          </div>

          {/* Search */}
          <div className="relative mb-8">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40" />
            <Input
              type="text"
              placeholder="Search terms..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              data-testid="terminology-search"
              className="pl-12 bg-[#0a0a0a] border-[#27272a] text-white placeholder:text-white/30 focus:border-[#FF0099] h-14 font-mono"
            />
          </div>

          {/* Info Box */}
          <div className="bg-[#0a0a0a] border border-[#27272a] p-4 mb-8 flex items-start gap-3">
            <Info className="w-5 h-5 text-[#00F0FF] mt-0.5 flex-shrink-0" />
            <p className="text-white/60 text-sm">
              New to card collecting? This glossary covers all the essential terms you'll encounter 
              when buying, selling, and trading sports cards. From grading abbreviations to pack types, 
              we've got you covered.
            </p>
          </div>

          {/* Terms List */}
          <div className="space-y-8">
            {sortedKeys.map((letter) => (
              <div key={letter}>
                <div className="sticky top-20 z-10 bg-[#050505] py-2">
                  <h2 className="font-heading text-3xl font-bold text-[#00F0FF]">{letter}</h2>
                </div>
                <div className="space-y-3">
                  {groupedTerms[letter].map((term, i) => (
                    <div
                      key={i}
                      data-testid={`term-${term.term.replace(/[^a-zA-Z0-9]/g, '-').toLowerCase()}`}
                      className="bg-[#0a0a0a] border border-[#27272a] p-4 hover:border-[#FF0099] transition-all"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-start gap-2">
                        <span className="font-mono text-[#FF0099] font-bold text-lg min-w-[120px]">
                          {term.term}
                        </span>
                        <span className="text-white/80">{term.meaning}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {filteredTerms.length === 0 && (
            <div className="text-center py-12">
              <p className="text-white/40 font-mono">No terms found matching "{search}"</p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
