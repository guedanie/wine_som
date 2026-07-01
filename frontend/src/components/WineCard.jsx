import { ThumbsUp, ThumbsDown } from 'lucide-react';
import Tag from './Tag.jsx';

const _THUMB_EASE = 'all 140ms cubic-bezier(.25,.46,.45,.94)';

function ThumbBtn({ direction, voted, onClick }) {
  const title = direction === 'up' ? 'Good pick' : 'Not for me';
  const Icon  = direction === 'up' ? ThumbsUp : ThumbsDown;
  return (
    <button
      type="button"
      title={title}
      onClick={e => { e.stopPropagation(); onClick(direction); }}
      style={{
        cursor: 'pointer',
        width: 26, height: 26,
        borderRadius: 2,
        border: voted ? '1px solid var(--brass)' : '1px solid var(--border)',
        background: voted ? 'var(--brass)' : 'transparent',
        color: voted ? 'var(--cream)' : 'var(--faded)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: _THUMB_EASE,
        padding: 0,
      }}
    >
      <Icon size={12} strokeWidth={1.75} />
    </button>
  );
}

export default function WineCard({ wine, onClick, vote, onVote }) {
  return (
    <div
      onClick={onClick}
      style={{ border: '1.5px solid var(--ink)', background: 'var(--cream)', cursor: onClick ? 'pointer' : 'default', transition: 'transform .18s var(--ease), box-shadow .18s var(--ease)' }}
      onMouseEnter={e => { if (onClick) { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--shadow-card)'; } }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
    >
      <div style={{ padding: '13px 14px', borderBottom: '0.75px solid var(--brass)', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          {wine.tagline && (
            <div style={{ fontSize: 9.5, letterSpacing: '0.24em', textTransform: 'uppercase', color: 'var(--faded)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {wine.tagline}
            </div>
          )}
          {wine.coord && (
            <div style={{ fontSize: 10, letterSpacing: '0.16em', color: 'var(--sage)', marginTop: 4 }}>{wine.coord}</div>
          )}
        </div>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--bordeaux)', flex: 'none' }}>${wine.price}</div>
      </div>
      <div style={{ padding: '13px 14px 14px' }}>
        <div style={{ fontFamily: 'var(--font-serif)', fontSize: 23, lineHeight: 1.05, color: 'var(--ink)' }}>{wine.name}</div>
        <div style={{ fontSize: 11.5, color: 'var(--ink-2)', marginTop: 3 }}>{wine.retailer}</div>
        {wine.flavors?.length > 0 && (
          <div style={{ display: 'flex', gap: 6, marginTop: 11, flexWrap: 'wrap' }}>
            {wine.flavors.map(t => <Tag key={t}>{t}</Tag>)}
          </div>
        )}
      </div>
      {onVote && (
        <div style={{ padding: '7px 12px 10px', borderTop: '0.75px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: 4 }}>
          <ThumbBtn direction="up"   voted={vote === 'up'}   onClick={onVote} />
          <ThumbBtn direction="down" voted={vote === 'down'} onClick={onVote} />
        </div>
      )}
    </div>
  );
}
