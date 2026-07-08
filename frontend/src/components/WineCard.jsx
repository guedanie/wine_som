import { ThumbsUp, ThumbsDown } from 'lucide-react';
import Tag from './Tag.jsx';
import SaveBookmark from './SaveBookmark.jsx';

const _THUMB_EASE = 'all 140ms cubic-bezier(.25,.46,.45,.94)';

function ThumbBtn({ direction, voted, onClick, size = 26 }) {
  const title = direction === 'up' ? 'Good pick' : 'Not for me';
  const Icon  = direction === 'up' ? ThumbsUp : ThumbsDown;
  return (
    <button
      type="button"
      title={title}
      onClick={e => { e.stopPropagation(); onClick(direction); }}
      style={{
        cursor: 'pointer',
        width: size, height: size,
        borderRadius: 2,
        border: voted ? '1px solid var(--brass)' : '1px solid var(--border)',
        background: voted ? 'var(--brass)' : 'transparent',
        color: voted ? 'var(--cream)' : 'var(--faded)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        transition: _THUMB_EASE,
        padding: 0,
      }}
    >
      <Icon size={size >= 40 ? 16 : 12} strokeWidth={1.75} />
    </button>
  );
}

function LandscapeCard({ wine, onClick, vote, onVote }) {
  return (
    <div
      onClick={onClick}
      style={{
        border: '1.5px solid var(--ink)', background: 'var(--cream)', position: 'relative',
        cursor: onClick ? 'pointer' : 'default', display: 'flex', alignItems: 'stretch',
        minHeight: 120, transition: 'transform .18s var(--ease), box-shadow .18s var(--ease)',
      }}
      onMouseEnter={e => { if (onClick) { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = '0 4px 16px rgba(26,26,26,.12)'; } }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
    >
      <SaveBookmark wine={wine} size={15} style={{ position: 'absolute', top: 4, right: 4, width: 32, height: 32, zIndex: 2 }} />
      {/* Left rail — tagline + coord above, price anchored bottom */}
      <div style={{ padding: '14px 16px', borderRight: '0.75px solid var(--brass)', minWidth: 130, maxWidth: 150, display: 'flex', flexDirection: 'column', gap: 8, flex: 'none' }}>
        <div>
          {wine.tagline && (
            <div style={{ fontSize: 9, letterSpacing: '0.24em', textTransform: 'uppercase', color: 'var(--faded)' }}>
              {wine.tagline}
            </div>
          )}
          {wine.coord && (
            <div style={{ fontSize: 9.5, letterSpacing: '0.14em', color: 'var(--sage)', marginTop: 5 }}>{wine.coord}</div>
          )}
        </div>
        {wine.price != null && <div style={{ fontFamily: 'var(--font-serif)', fontSize: 26, color: 'var(--bordeaux)', marginTop: 'auto' }}>${wine.price}</div>}
      </div>

      {/* Body — name, meta, tags; thumbs bottom-right */}
      <div style={{ padding: '14px 16px', flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-serif)', fontSize: 20, lineHeight: 1.1, color: 'var(--ink)' }}>{wine.name}</div>
          <div style={{ fontSize: 11.5, color: 'var(--ink-2)', marginTop: 3 }}>{wine.retailer}</div>
          {wine.vivino_rating && wine.vivino_ratings_count > 0 && (
            <div style={{ fontSize: 11, color: 'var(--sage)', marginTop: 3 }}>
              {wine.vivino_rating.toFixed(1)} ★ · {wine.vivino_ratings_count >= 1000
                ? `${Math.round(wine.vivino_ratings_count / 1000)}k`
                : wine.vivino_ratings_count} on Vivino
            </div>
          )}
          {wine.flavors?.length > 0 && (
            <div style={{ display: 'flex', gap: 5, marginTop: 10, flexWrap: 'wrap' }}>
              {wine.flavors.map(t => <Tag key={t}>{t}</Tag>)}
            </div>
          )}
        </div>
        {onVote && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 5, marginTop: 'auto', paddingTop: 6 }}>
            <ThumbBtn direction="up"   voted={vote === 'up'}   onClick={onVote} />
            <ThumbBtn direction="down" voted={vote === 'down'} onClick={onVote} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function WineCard({ wine, onClick, vote, onVote, variant, voteSize = 26 }) {
  if (variant === 'landscape') {
    return <LandscapeCard wine={wine} onClick={onClick} vote={vote} onVote={onVote} />;
  }
  return (
    <div
      onClick={onClick}
      style={{ border: '1.5px solid var(--ink)', background: 'var(--cream)', cursor: onClick ? 'pointer' : 'default', transition: 'transform .18s var(--ease), box-shadow .18s var(--ease)' }}
      onMouseEnter={e => { if (onClick) { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--shadow-card)'; } }}
      onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
    >
      <div style={{ padding: '13px 14px', borderBottom: '0.75px solid var(--brass)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
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
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, flex: 'none' }}>
          <SaveBookmark wine={wine} size={15} style={{ width: 30, height: 30 }} />
          {wine.price != null && <div style={{ fontFamily: 'var(--font-serif)', fontSize: 24, color: 'var(--bordeaux)' }}>${wine.price}</div>}
        </div>
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
        <div style={{ padding: '7px 12px 10px', borderTop: '0.75px solid var(--border)', display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
          <ThumbBtn direction="up"   voted={vote === 'up'}   onClick={onVote} size={voteSize} />
          <ThumbBtn direction="down" voted={vote === 'down'} onClick={onVote} size={voteSize} />
        </div>
      )}
    </div>
  );
}
