import React from 'react';

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <div className={`skeleton-shimmer ${className}`} />;
}

function SkeletonCard() {
  return (
    <div className="glass-panel overflow-hidden">
      {/* Header row */}
      <div className="p-4 border-b border-white/10 flex justify-between items-center bg-slate-800/50">
        <div className="flex items-center gap-3">
          <SkeletonBlock className="skeleton-badge" />
          <SkeletonBlock className="skeleton-text-md" />
        </div>
        <SkeletonBlock className="skeleton-text-sm" />
      </div>

      {/* Body */}
      <div className="p-6 flex flex-col gap-4">
        {/* Symptoms label */}
        <SkeletonBlock className="skeleton-text-xs" />
        {/* Symptom tags */}
        <div className="flex gap-2">
          <SkeletonBlock className="skeleton-tag" />
          <SkeletonBlock className="skeleton-tag" />
          <SkeletonBlock className="skeleton-tag" />
        </div>
        {/* Action block */}
        <div className="mt-2 p-5 rounded-lg border border-slate-700/40 bg-slate-800/20">
          <SkeletonBlock className="skeleton-text-xs" />
          <SkeletonBlock className="skeleton-text-lg" />
          <SkeletonBlock className="skeleton-code-block" />
          <div className="flex gap-3 mt-4">
            <SkeletonBlock className="skeleton-button" />
            <SkeletonBlock className="skeleton-button-sm" />
          </div>
        </div>
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <SkeletonBlock className="skeleton-heading" />
      {[0, 1, 2].map((i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}

export default LoadingSkeleton;
