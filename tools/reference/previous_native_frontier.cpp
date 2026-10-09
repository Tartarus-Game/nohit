// Exact active-battle equations. No fast-math, quantization or saved routes.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <exception>
#include <limits>
#include <thread>
#include <condition_variable>
#include <mutex>
#include <functional>
#include <vector>
#if defined(_WIN32)
#define NOMINMAX
#include <windows.h>
#else
#include <time.h>
#endif

struct JoinThreads {
    std::vector<std::thread>& threads;
    ~JoinThreads(){for(auto& thread:threads)if(thread.joinable())thread.join();}
};
struct State { double v[11]; };
struct World {
    const double *env, *platforms, *white, *blue, *polygons;
    int nt, np, nw, nb, nq;
    const double* row(int t) const { return env + t*22; }
    const double* platform(int t) const { return platforms + size_t(t)*np*9; }
};
struct Stats {
    uint64_t expanded=0, generated=0, unique=0, discarded=0, workspace_bytes=0, preview_steps=0, recovery_steps=0, recoveries=0, cpu_nanoseconds=0;
    int32_t reached=0, status=0;
};
static uint64_t thread_cpu_ns() {
#if defined(_WIN32)
    FILETIME created,exit,kernel,user;
    if(!GetThreadTimes(GetCurrentThread(),&created,&exit,&kernel,&user))return 0;
    ULARGE_INTEGER k,u;k.LowPart=kernel.dwLowDateTime;k.HighPart=kernel.dwHighDateTime;
    u.LowPart=user.dwLowDateTime;u.HighPart=user.dwHighDateTime;
    return (k.QuadPart+u.QuadPart)*100;
#else
    timespec value{};
    if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&value)!=0)return 0;
    return uint64_t(value.tv_sec)*1000000000ULL+uint64_t(value.tv_nsec);
#endif
}
struct CpuAccounting {
    Stats& stats;uint64_t began;
    explicit CpuAccounting(Stats& value):stats(value),began(thread_cpu_ns()){}
    ~CpuAccounting(){stats.cpu_nanoseconds+=thread_cpu_ns()-began;}
};

// Persistent workers share immutable frame tensors and disjoint edge slots.
// The caller compacts/deduplicates in source parent/control order afterwards.
class EdgeTeam {
    std::mutex mutex;std::condition_variable wake,finished;
    std::vector<std::thread> threads;std::vector<uint64_t> cpu;
    std::function<void(int,int)> task;
    int total=1,count=0,remaining=0;uint64_t generation=0;bool stopping=false;
public:
    explicit EdgeTeam(int workers):cpu(workers,0),total(workers) {
        try {for(int i=1;i<workers;i++)threads.emplace_back([&,i](){
            uint64_t began=thread_cpu_ns(),seen=0;
            std::unique_lock<std::mutex> lock(mutex);
            for(;;){wake.wait(lock,[&](){return stopping || generation!=seen;});
                if(stopping)break;seen=generation;int n=count;
                lock.unlock();task(n*i/total,n*(i+1)/total);lock.lock();
                if(--remaining==0)finished.notify_one();
            }
            cpu[i]=thread_cpu_ns()-began;
        });}catch(...){stop();throw;}
    }
    void stop(){ {std::lock_guard<std::mutex> lock(mutex);stopping=true;}wake.notify_all();
        for(auto& thread:threads)if(thread.joinable())thread.join(); }
    ~EdgeTeam(){stop();}
    template<class F>void run(int n,F function){
        if(total==1 || n<128){function(0,n);return;}
        {std::lock_guard<std::mutex> lock(mutex);task=function;count=n;remaining=total-1;generation++;}
        wake.notify_all();function(0,n/total);
        std::unique_lock<std::mutex> lock(mutex);finished.wait(lock,[&](){return remaining==0;});
    }
    uint64_t finish_cpu(){stop();uint64_t value=0;for(auto n:cpu)value+=n;return value;}
};
static bool overlap(double x,double y,double l,double t,double r,double b) {
    return x+8.>=l && x-8.<=r && y+8.>=t && y-8.<=b;
}
static bool solid(double x,double y,double dy,double dir,const double* e,
                  const double* platforms,int np,double ox=0.,double oy=0.,bool old=false) {
    const int j=old?14:18;
    const double l=e[j],t=e[j+1],r=e[j+2],b=e[j+3],qx=x+ox,qy=y+oy;
    if(overlap(qx,qy,l,t,r,t+5.) || overlap(qx,qy,l,t,l+5.,b) ||
       overlap(qx,qy,l,b-5.,r,b) || overlap(qx,qy,r-5.,t,r,b))return true;
    // Match the existing source operator, including its downward-only platform contract.
    if(dir==1.)for(int i=0;i<np;i++) {
        const double* p=platforms+i*9;
        if(p[old?7:6] && overlap(qx,qy,p[0],p[1],p[0]+p[2],p[1]+p[3]) &&
           p[1]>y && dy>=p[old?8:5] && y+8.<=p[1]+2.)return true;
    }
    return false;
}
static void clamp(double& x,double& y,const double* e,int j) {
    if(overlap(x,y,e[j],e[j+1],e[j+2],e[j+3])) {
        if(e[j]+5.>x-8.)x=e[j]+5.+8.;
        if(e[j+1]+5.>y-8.)y=e[j+1]+5.+8.;
        if(e[j+2]-5.<x+8.)x=e[j+2]-5.-8.;
        if(e[j+3]-5.<y+8.)y=e[j+3]-5.-8.;
    }
}
static void step(const State& s,int mask,const double* e,const double* p,int np,State& out) {
    double x=s.v[0],y=s.v[1],dx=s.v[2],dy=s.v[3],slammed=s.v[5],dir=s.v[7];
    double maxfall=s.v[8],slamdamage=s.v[9],damage=0.,dt=e[7];
    const double mx=dx*dt,my=dy*dt;
    if(mx!=0.) {
        const double start=x;
        const int count=std::max(1,int(std::floor(std::sqrt(mx*mx)+.5)));
        for(int i=1;i<=count;i++) {
            double candidate=start+mx*(double(i)/count);
            if(solid(candidate,y,dy,dir,e,p,np,0.,0.,true)) {
                if(slammed){slammed=0.;if(std::abs(dx)>=330. && slamdamage)damage=1.;}
                if(dx!=0.){dx=0.;x=start+mx*(double(i-1)/count);break;}
            }
            x=candidate;
        }
    }
    if(my!=0.) {
        const double start=y;
        const int count=std::max(1,int(std::floor(std::sqrt(my*my)+.5)));
        for(int i=1;i<=count;i++) {
            double candidate=start+my*(double(i)/count);
            if(solid(x,candidate,dy,dir,e,p,np,0.,0.,true)) {
                if(slammed){slammed=0.;if(std::abs(dy)>=330. && slamdamage)damage=1.;}
                if(dy!=0.){dy=0.;y=start+my*(double(i-1)/count);break;}
            }
            y=candidate;
        }
    }
    const int previous=int(s.v[4]);
    double mode=e[4];dir=e[5];maxfall=e[8];slamdamage=e[12];
    if(e[18]!=e[14] || e[19]!=e[15] || e[20]!=e[16] || e[21]!=e[17])clamp(x,y,e,18);
    if(e[9]){x=e[10];y=e[11];}
    const double angle=dir*(3.141592653589793/2.);
    const double gx=std::cos(angle),gy=std::sin(angle);
    if(e[6]){mode=1.;dx=gx*maxfall;dy=gy*maxfall;slammed=1.;}
    const double speed=(mask&16)?75.:150.;
    const int ux=((mask&2)?1:0)-((mask&1)?1:0),up=((mask&4)?1:0)-((mask&8)?1:0);
    if(mode==0.){dx=ux*speed;dy=-up*speed;}
    else {
        const int jump=dir==0.?1:dir==1.?4:dir==2.?2:8;
        if((mask&jump) && !(previous&jump) && solid(x,y,dy,dir,e,p,np,gx,gy)) {
            dx=dx-gx*180.;dy=dy-gy*180.;
        }
        if((previous&jump) && !(mask&jump)) {
            if(dir==0. && dx < -30.)dx=-30.;
            else if(dir==1. && dy < -30.)dy=-30.;
            else if(dir==2. && dx > 30.)dx=30.;
            else if(dir==3. && dy > 30.)dy=30.;
        }
        const double down=dir==0.?dx:dir==1.?dy:dir==2.?-dx:-dy;
        double gravity=0.;
        if(15.<down && down<240.)gravity=540.;
        else if(-30.<down && down<=15.)gravity=180.;
        else if(-120.<down && down<=-30.)gravity=450.;
        else if(down<=-120.)gravity=180.;
        if(!solid(x,y,dy,dir,e,p,np,gx*.2,gy*.2)) {
            dx=dx+gx*gravity*dt;dy=dy+gy*gravity*dt;
            if(dir==0. && dx>maxfall)dx=maxfall;
            else if(dir==1. && dy>maxfall)dy=maxfall;
            else if(dir==2. && dx < -maxfall)dx=-maxfall;
            else if(dir==3. && dy < -maxfall)dy=-maxfall;
        }
        if(dir==0. || dir==2.)dy=-up*speed;
        else {
            dx=0.;
            if(dir==1.)for(int i=0;i<np;i++) {
                const double* q=p+i*9;
                if(q[6] && overlap(x+gx*.5,y+gy*.5,q[0],q[1],q[0]+q[2],q[1]+q[3]) &&
                   dy>=q[5] && y+8.<=q[1]+2.){dx=q[4];dy=q[5];y=q[1]-8.05;}
            }
            dx=dx+ux*speed;
        }
    }
    clamp(x,y,e,0);
    out={{x,y,dx,dy,double(mask),slammed,mode,dir,maxfall,slamdamage,damage}};
}
static bool quad_hit(const double* q,double x,double y) {
    if(!std::isfinite(q[0]))return false;
    double l=q[0],r=l,t=q[1],b=t;
    for(int i=1;i<4;i++){l=std::min(l,q[i*2]);r=std::max(r,q[i*2]);t=std::min(t,q[i*2+1]);b=std::max(b,q[i*2+1]);}
    if(x+2.<l || x-2.>r || y+2.<t || y-2.>b)return false;
    for(int i=0;i<4;i++) {
        int k=(i+1)%4;
        double ax=-(q[k*2+1]-q[i*2+1]),ay=q[k*2]-q[i*2];
        double lo=ax*q[0]+ay*q[1],hi=lo;
        for(int m=1;m<4;m++){double dot=ax*q[m*2]+ay*q[m*2+1];lo=std::min(lo,dot);hi=std::max(hi,dot);}
        double mid=ax*x+ay*y,radius=std::abs(ax)*2.+std::abs(ay)*2.;
        if(mid+radius<lo || mid-radius>hi)return false;
    }
    return true;
}
static bool collision(const World& w,int tick,const State& s) {
    if(s.v[10]!=0.)return true;
    const double x=s.v[0],y=s.v[1];
    for(int plane=0;plane<2;plane++) {
        if(plane && s.v[2]==0. && s.v[3]==0.)continue;
        const int n=plane?w.nb:w.nw;
        const double* boxes=(plane?w.blue:w.white)+size_t(tick)*n*4;
        for(int i=0;i<n;i++) {
            const double* b=boxes+i*4;
            if(x+2.>=b[0] && x-2.<=b[2] && y+2.>=b[1] && y-2.<=b[3])return true;
        }
    }
    const double* polys=w.polygons+size_t(tick)*w.nq*8;
    for(int i=0;i<w.nq;i++)if(quad_hit(polys+i*8,x,y))return true;
    return false;
}
static uint32_t random32(uint32_t& x){x^=x<<13;x^=x>>17;x^=x<<5;return x;}
static uint64_t word(double x){uint64_t v;std::memcpy(&v,&x,8);return v;}
static uint64_t hash_state(const State& s,int bit) {
    uint64_t h=0xcbf29ce484222325ULL;
    for(int i=0;i<11;i++)h=(h ^ word(i==4 && bit>=0?double(int(s.v[4])&bit):s.v[i]))*0x100000001b3ULL;
    return h;
}
static bool equal_state(const State& a,const State& b,int bit) {
    for(int i=0;i<11;i++)if(i==4 && bit>=0) {
        if((int(a.v[4])&bit)!=(int(b.v[4])&bit))return false;
    }else if(word(a.v[i])!=word(b.v[i]))return false;
    return true;
}
// Exact parent indices need only 16 bits for ordinary bounded frontiers.
// Wider callers retain 32-bit storage; neither path changes state arithmetic.
class PackedParents {
    bool compact;std::vector<uint16_t> narrow;std::vector<uint32_t> wide;
public:
    PackedParents(size_t count,int width):compact(width<=65535),
        narrow(compact?count:0),wide(compact?0:count){}
    uint64_t bytes()const{return narrow.size()*2+wide.size()*4;}
    uint32_t get(size_t index)const{return compact?uint32_t(narrow[index]):wide[index];}
    void set(size_t index,uint32_t value){if(compact)narrow[index]=uint16_t(value);else wide[index]=value;}
    struct Reference {PackedParents& rows;size_t index;
        operator uint32_t()const{return rows.get(index);}
        Reference& operator=(uint32_t value){rows.set(index,value);return *this;}};
    Reference operator[](size_t index){return {*this,index};}
};
struct Snapshot {std::array<double,4> motion;double slammed;int32_t cost;uint8_t mask;};
struct Edge {State state;uint32_t parent;int32_t cost;uint32_t tie;uint8_t mask;};
// A low-speed perpendicular wall contact can clear Slammed before a
// damaging primary-axis landing. This ranks candidates only; actual source
// movement and damage checks still decide whether any edge is admissible.
static int slam_escape_rank(const State& s,const double* e) {
    if(!s.v[9])return 0;
    if(!s.v[5])return 100;
    const bool horizontal=s.v[7]==0. || s.v[7]==2.;
    const double primary=horizontal?s.v[2]:s.v[3];
    if(std::abs(primary)<330.)return 100;
    const double perpendicular=horizontal?s.v[3]:s.v[2];
    if(std::abs(perpendicular)<1.)return -100;
    const double primary_gap=horizontal?(primary>0.?e[2]-13.-s.v[0]:s.v[0]-e[0]-13.):
        (primary>0.?e[3]-13.-s.v[1]:s.v[1]-e[1]-13.);
    const double escape_gap=horizontal?(perpendicular>0.?e[3]-13.-s.v[1]:s.v[1]-e[1]-13.):
        (perpendicular>0.?e[2]-13.-s.v[0]:s.v[0]-e[0]-13.);
    const double advantage=primary_gap/std::abs(primary)-escape_gap/std::abs(perpendicular);
    return int(std::max(-99.,std::min(99.,advantage*100.)));
}
using Bucket=std::array<int64_t,5>;
static Bucket bucket(const State& s){return {{int64_t(std::floor(s.v[0]/5.)),int64_t(std::floor(s.v[1]/5.)),int64_t(std::floor(s.v[2]/30.)),int64_t(std::floor(s.v[3]/30.)),int64_t(s.v[5])}};}
static uint64_t hash_bucket(const Bucket& b){uint64_t h=0xcbf29ce484222325ULL;for(auto x:b)h=(h ^ uint64_t(x))*0x100000001b3ULL;return h;}
using Clock=std::chrono::steady_clock;
static bool probe(const World& w,const State& initial,const int64_t* controls,const int64_t* counts,
                  int stride,int width,uint32_t seed,int job,std::atomic<int>& best,
                  Clock::time_point deadline,int64_t* actions,Stats& stats,int inner_workers) {
    CpuAccounting cpu(stats);
    inner_workers=width>=256?inner_workers:1;
    EdgeTeam team(inner_workers);
    struct TeamCpu {EdgeTeam& team;Stats& stats;~TeamCpu(){stats.cpu_nanoseconds+=team.finish_cpu();}} team_cpu{team,stats};
    const int maxedges=width*stride;
    std::vector<State> current(width),next(width);
    std::vector<int32_t> costs(width),nextcosts(width);
    PackedParents ancestry(size_t(w.nt)*width,width);
    std::vector<uint8_t> masks(size_t(w.nt)*width);
    const int history_frames=width>=512?64:0;
    std::vector<Snapshot> snapshots(size_t(history_frames)*width);
    std::vector<int> snapshot_counts(history_frames),snapshot_ticks(history_frames,-1);
    auto capture=[&](int tick,const std::vector<State>& states,const std::vector<int32_t>& costs,int count){
        if(!history_frames)return;const int row=tick%history_frames;
        snapshot_counts[row]=count;snapshot_ticks[row]=tick;
        for(int i=0;i<count;i++){const State& s=states[i];
            snapshots[size_t(row)*width+i]={{{s.v[0],s.v[1],s.v[2],s.v[3]}},s.v[5],costs[i],uint8_t(s.v[4])};}
    };
    auto restore=[&](int tick,int index){if(tick==0)return initial;
        const Snapshot& item=snapshots[size_t(tick%history_frames)*width+index];const double* row=w.row(tick);
        return State{{item.motion[0],item.motion[1],item.motion[2],item.motion[3],double(item.mask),
            item.slammed,row[6]?1.:row[4],row[5],row[8],row[12],0.}};
    };
    std::vector<Edge> staged(inner_workers>1?maxedges:0);
    std::vector<uint8_t> accepted(inner_workers>1?maxedges:0);
    std::vector<Edge> edges;edges.reserve(maxedges);
    std::vector<int> order,reps,selected;order.reserve(maxedges);reps.reserve(maxedges);selected.reserve(width);
    std::vector<uint8_t> used(maxedges);std::vector<int32_t> viability(maxedges);
    size_t capacity=8;while(capacity<size_t(maxedges)*2)capacity*=2;
    std::vector<int32_t> table(capacity,-1);
    stats.workspace_bytes=(2*size_t(width)*sizeof(State)+2*size_t(width)*4+
        ancestry.bytes()+size_t(w.nt)*width+size_t(maxedges)*(sizeof(Edge)+13)+size_t(width)*4+capacity*4);
    stats.workspace_bytes+=staged.size()*(sizeof(Edge)+1)+snapshots.size()*sizeof(Snapshot)+history_frames*8;
    const uint64_t base_workspace=stats.workspace_bytes;
    current[0]=initial;int count=1;uint32_t rng=seed?seed:0x6d2b79f5U;
    capture(0,current,costs,count);
    for(int tick=1;tick<w.nt;tick++) {
        stats.reached=tick-1;
        if(best.load(std::memory_order_relaxed)<job || Clock::now()>=deadline){stats.status=2;return false;}
        edges.clear();std::fill(table.begin(),table.end(),-1);
        const double* e=w.row(tick),*p=w.platform(tick);
        const bool blue=e[4]!=0. || e[6]!=0.;
        const int jump=e[5]==0.?1:e[5]==1.?4:e[5]==2.?2:8;
        int bit=-1;
        if(tick+1<w.nt){const double* en=w.row(tick+1);bit=(en[4]!=0. || en[6]!=0.)?(en[5]==0.?1:en[5]==1.?4:en[5]==2.?2:8):0;}
        if(inner_workers==1) {
        for(int parent=0;parent<count;parent++) {
            State bases[2];bool prepared[2]={false,false};int safe[2][2]={{-1,-1},{-1,-1}};
            for(int ci=0;ci<counts[tick-1];ci++) {
                int mask=int(controls[(tick-1)*stride+ci]);int branch=int(blue && (mask&jump));
                if(!prepared[branch]){step(current[parent],branch?jump:0,e,p,w.np,bases[branch]);prepared[branch]=true;}
                State state=bases[branch];double speed=(mask&16)?75.:150.;
                int ux=((mask&2)?1:0)-((mask&1)?1:0),up=((mask&4)?1:0)-((mask&8)?1:0);
                if(!blue){state.v[2]=ux*speed;state.v[3]=-up*speed;}
                else if(e[5]==0. || e[5]==2.)state.v[3]=-up*speed;
                else state.v[2]=bases[branch].v[2]+ux*speed;
                state.v[4]=mask;
                const int moving=int(state.v[2]!=0. || state.v[3]!=0.);
                if(safe[branch][moving]<0)safe[branch][moving]=!collision(w,tick,state);
                if(!safe[branch][moving])continue;
                stats.generated++;
                size_t slot=hash_state(state,bit)&(capacity-1);
                while(table[slot]>=0 && !equal_state(state,edges[table[slot]].state,bit))slot=(slot+1)&(capacity-1);
                if(table[slot]>=0)continue;
                table[slot]=int(edges.size());
                const int cost=costs[parent]+(mask!=int(current[parent].v[4])?12:0)+(mask?1:0);
                edges.push_back({state,uint32_t(parent),cost,random32(rng),uint8_t(mask)});
            }
        }
        }
        else {
            team.run(count,[&](int first,int last){for(int parent=first;parent<last;parent++) {
                State bases[2];bool prepared[2]={false,false};int safe[2][2]={{-1,-1},{-1,-1}};
                for(int ci=0;ci<counts[tick-1];ci++) {
                    const int slot=parent*stride+ci;accepted[slot]=0;
                    int mask=int(controls[(tick-1)*stride+ci]);int branch=int(blue && (mask&jump));
                    if(!prepared[branch]){step(current[parent],branch?jump:0,e,p,w.np,bases[branch]);prepared[branch]=true;}
                    State state=bases[branch];double speed=(mask&16)?75.:150.;
                    int ux=((mask&2)?1:0)-((mask&1)?1:0),up=((mask&4)?1:0)-((mask&8)?1:0);
                    if(!blue){state.v[2]=ux*speed;state.v[3]=-up*speed;}
                    else if(e[5]==0. || e[5]==2.)state.v[3]=-up*speed;
                    else state.v[2]=bases[branch].v[2]+ux*speed;
                    state.v[4]=mask;
                    const int moving=int(state.v[2]!=0. || state.v[3]!=0.);
                    if(safe[branch][moving]<0)safe[branch][moving]=!collision(w,tick,state);
                    if(!safe[branch][moving])continue;
                    int cost=costs[parent]+(mask!=int(current[parent].v[4])?12:0)+(mask?1:0);
                    staged[slot]={state,uint32_t(parent),cost,0,uint8_t(mask)};accepted[slot]=1;
                }
            }});
            for(int parent=0;parent<count;parent++)for(int ci=0;ci<counts[tick-1];ci++) {
                int slot=parent*stride+ci;if(!accepted[slot])continue;
                stats.generated++;const State& state=staged[slot].state;
                size_t hash=hash_state(state,bit)&(capacity-1);
                while(table[hash]>=0 && !equal_state(state,edges[table[hash]].state,bit))hash=(hash+1)&(capacity-1);
                if(table[hash]>=0)continue;
                table[hash]=int(edges.size());staged[slot].tie=random32(rng);edges.push_back(staged[slot]);
            }
        }
        stats.expanded+=count;stats.unique+=edges.size();
        if(edges.empty()) {
            // Recover before declaring a width-pruned prefix exhausted. State
            // snapshots are reconstructed from compact ancestry only on demand.
            std::vector<uint8_t> seen(width);
            std::vector<int64_t> wordbuf(w.nt);
            std::vector<int> origins;origins.reserve(width);
            stats.workspace_bytes=base_workspace+size_t(width)*(1+4)+size_t(w.nt)*8;
            for(int lookback: {4,8,12,16,24,32,48,64,96,128,192,256}) {
                const int start=std::max(0,tick-lookback);
                if(best.load()<job || Clock::now()>=deadline){stats.status=2;return false;}
                origins.clear();std::fill(seen.begin(),seen.end(),0);
                const bool retained=history_frames && snapshot_ticks[start%history_frames]==start;
                if(retained){for(int i=0;i<snapshot_counts[start%history_frames];i++)origins.push_back(i);}
                else for(int index=0;index<count;index++) {
                    int ancestor=index;
                    for(int t=tick-1;t>start;t--)ancestor=int(ancestry[size_t(t)*width+ancestor]);
                    if(!seen[ancestor]){seen[ancestor]=1;origins.push_back(ancestor);}
                }
                for(int origin:origins) {
                    if(best.load()<job || Clock::now()>=deadline){stats.status=2;return false;}
                    State origin_state;int basecost=0;
                    if(retained){origin_state=restore(start,origin);basecost=snapshots[size_t(start%history_frames)*width+origin].cost;}
                    else {
                        int ancestor=origin;
                        for(int t=start;t>0;t--){wordbuf[t-1]=masks[size_t(t)*width+ancestor];ancestor=int(ancestry[size_t(t)*width+ancestor]);}
                        origin_state=initial;
                        for(int t=1;t<=start;t++) {
                            int mask=int(wordbuf[t-1]);basecost+=(mask!=int(origin_state.v[4])?12:0)+(mask?1:0);
                            State following;step(origin_state,mask,w.row(t),w.platform(t),w.np,following);origin_state=following;stats.recovery_steps++;
                        }
                    }
                    for(int mask=0;mask<16;mask++) {
                        State simulated=origin_state;bool safe=true;int cost=basecost;
                        for(int t=start+1;t<=tick;t++) {
                            State following;step(simulated,mask,w.row(t),w.platform(t),w.np,following);stats.recovery_steps++;
                            if(collision(w,t,following)){safe=false;break;}
                            cost+=(mask!=int(simulated.v[4])?12:0)+(mask?1:0);simulated=following;
                        }
                        if(safe)edges.push_back({simulated,uint32_t(origin),cost,random32(rng),uint8_t(mask)});
                    }
                }
                if(edges.empty())continue;
                order.resize(edges.size());for(size_t i=0;i<edges.size();i++)order[i]=int(i);
                std::sort(order.begin(),order.end(),[&](int a,int b){return edges[a].cost!=edges[b].cost?edges[a].cost<edges[b].cost:edges[a].tie<edges[b].tie;});
                const int keep=std::min(width,int(order.size()));
                if(history_frames)for(int t=start+1;t<tick;t++)
                    if(snapshot_ticks[t%history_frames]==t)snapshot_ticks[t%history_frames]=-1;
                for(int i=0;i<keep;i++) {
                    const Edge& edge=edges[order[i]];next[i]=edge.state;nextcosts[i]=edge.cost;
                    for(int t=start+1;t<=tick;t++) {
                        ancestry[size_t(t)*width+i]=(t==start+1)?edge.parent:uint32_t(i);
                        masks[size_t(t)*width+i]=edge.mask;
                    }
                }
                current.swap(next);costs.swap(nextcosts);count=keep;stats.recoveries++;break;
            }
            if(edges.empty()){stats.status=0;return false;}
            capture(tick,current,costs,count);
            continue;
        }
        order.resize(edges.size());
        for(size_t i=0;i<order.size();i++)order[i]=int(i);
        // Independent portfolio styles may rank real exits by exact held-input
        // lookahead. Preview states are never committed as a route or proof.
        const int horizon=job<3?0:12+12*(job%3);
        for(size_t index=0;index<edges.size();index++) {
            if(horizon && index%32==0 && (best.load()<job || Clock::now()>=deadline)){stats.status=2;return false;}
            int score=0;
            for(int variant=0;variant<(horizon?2:0);variant++) {
                State simulated=edges[index].state;int survived=0;
                int mask=variant?0:edges[index].mask;
                for(int future=tick+1;future<w.nt && future<=tick+horizon;future++) {
                    State following;step(simulated,mask,w.row(future),w.platform(future),w.np,following);
                    stats.preview_steps++;
                    if(collision(w,future,following))break;
                    survived++;simulated=following;
                }
                score=std::max(score,survived);
            }
            viability[index]=score+(width>=512?slam_escape_rank(edges[index].state,e):0);
        }
        auto less=[&](int a,int b){if(viability[a]!=viability[b])return viability[a]>viability[b];if(edges[a].cost!=edges[b].cost)return edges[a].cost<edges[b].cost;
            if(edges[a].tie!=edges[b].tie)return edges[a].tie<edges[b].tie;return a<b;};
        std::sort(order.begin(),order.end(),less);
        selected.clear();
        if(int(order.size())<=width)selected=order;
        else {
            std::fill(table.begin(),table.end(),-1);reps.clear();
            for(int index:order) {
                const Bucket key=bucket(edges[index].state);size_t slot=hash_bucket(key)&(capacity-1);
                while(table[slot]>=0 && bucket(edges[table[slot]].state)!=key)slot=(slot+1)&(capacity-1);
                if(table[slot]<0){table[slot]=index;reps.push_back(index);}
            }
            // Representatives already have the same cost/tie ordering.
            std::fill(used.begin(),used.begin()+edges.size(),0);
            for(int index:reps){if(int(selected.size())==width)break;selected.push_back(index);used[index]=1;}
            for(int index:order){if(int(selected.size())==width)break;if(!used[index])selected.push_back(index);}
        }
        stats.discarded+=edges.size()-selected.size();count=int(selected.size());
        for(int i=0;i<count;i++) {
            const Edge& edge=edges[selected[i]];next[i]=edge.state;nextcosts[i]=edge.cost;
            ancestry[size_t(tick)*width+i]=edge.parent;masks[size_t(tick)*width+i]=edge.mask;
        }
        current.swap(next);costs.swap(nextcosts);
        capture(tick,current,costs,count);
    }
    int winner=0;for(int i=1;i<count;i++)if(costs[i]<costs[winner])winner=i;
    for(int tick=w.nt-1;tick>0;tick--){actions[tick-1]=masks[size_t(tick)*width+winner];winner=int(ancestry[size_t(tick)*width+winner]);}
    stats.reached=w.nt-1;stats.status=1;
    int prior=best.load();while(job<prior && !best.compare_exchange_weak(prior,job)){}
    return true;
}
extern "C" {
// ABI widths are fixed; callers validate contiguous arrays and resource limits.
int nohit_expand(const double* states,int n,const int64_t* controls,int nc,
                 const double* env,int nt,const double* platforms,int np,
                 const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,
                 int tick,int workers,double* output,int64_t* parents,int64_t* masks) {
    try {
        World world{env,platforms,white,blue,polygons,nt,np,nw,nb,nq};
        std::vector<int> counts(n);
        const double* e=world.row(tick),*p=world.platform(tick);
        const bool blue_mode=e[4]!=0. || e[6]!=0.;
        const int jump=e[5]==0.?1:e[5]==1.?4:e[5]==2.?2:8;
        auto chunk=[&](int first,int last) {
            for(int parent=first;parent<last;parent++) {
                State in,bases[2];std::memcpy(in.v,states+parent*11,88);
                bool prepared[2]={false,false};int safe[2][2]={{-1,-1},{-1,-1}},count=0;
                for(int ci=0;ci<nc;ci++) {
                    const int mask=int(controls[ci]),branch=int(blue_mode && (mask&jump));
                    if(!prepared[branch]){step(in,branch?jump:0,e,p,np,bases[branch]);prepared[branch]=true;}
                    State state=bases[branch];const double speed=(mask&16)?75.:150.;
                    const int ux=((mask&2)?1:0)-((mask&1)?1:0),up=((mask&4)?1:0)-((mask&8)?1:0);
                    if(!blue_mode){state.v[2]=ux*speed;state.v[3]=-up*speed;}
                    else if(e[5]==0. || e[5]==2.)state.v[3]=-up*speed;
                    else state.v[2]=bases[branch].v[2]+ux*speed;
                    state.v[4]=mask;const int moving=int(state.v[2]!=0. || state.v[3]!=0.);
                    if(safe[branch][moving]<0)safe[branch][moving]=!collision(world,tick,state);
                    if(!safe[branch][moving])continue;
                    const size_t destination=size_t(parent)*nc+count++;
                    std::memcpy(output+destination*11,state.v,88);masks[destination]=mask;
                }
                counts[parent]=count;
            }
        };
        workers=std::max(1,std::min(workers,n));std::vector<std::thread> threads;JoinThreads joiner{threads};
        for(int i=1;i<workers;i++)threads.emplace_back(chunk,int(int64_t(n)*i/workers),int(int64_t(n)*(i+1)/workers));
        chunk(0,n/workers);for(auto& thread:threads)thread.join();
        size_t count=0;
        for(int parent=0;parent<n;parent++) {
            const size_t source=size_t(parent)*nc,keep=counts[parent];
            if(keep){std::memmove(output+count*11,output+source*11,keep*88);std::memmove(masks+count,masks+source,keep*8);}
            for(size_t i=0;i<keep;i++)parents[count+i]=parent;
            count+=keep;
        }
        return int(count);
    }catch(...){return -1;}
}
int nohit_step(const double* states,int n,const int64_t* masks,const double* env,const double* platforms,int np,double* output) {
    for(int i=0;i<n;i++){State in,out;std::memcpy(in.v,states+i*11,88);step(in,int(masks[i]),env,platforms,np,out);std::memcpy(output+i*11,out.v,88);}return 0;
}
int nohit_collision(const double* states,int n,const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,uint8_t* output) {
    World world{nullptr,nullptr,white,blue,polygons,1,0,nw,nb,nq};
    for(int i=0;i<n;i++){State s;std::memcpy(s.v,states+i*11,88);output[i]=collision(world,0,s);}return 0;
}
int nohit_search(const double* initial,const double* env,int nt,const double* platforms,int np,
                 const double* white,int nw,const double* blue,int nb,const double* polygons,int nq,
                 const int64_t* controls,const int64_t* counts,int stride,const int32_t* widths,
                 const uint32_t* seeds,int jobs,int workers,double seconds,int64_t* actions,
                 double* trace,Stats* stats,int32_t* controller_delay) {
    try {
        World world{env,platforms,white,blue,polygons,nt,np,nw,nb,nq};State state;std::memcpy(state.v,initial,88);
        if(collision(world,0,state))return -2;
        const auto deadline=Clock::now()+std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(seconds));
        *controller_delay=-1;
        // Cheap generic policies jump after exact ground contact. They contain
        // no attack names or routes; every accepted tick passes the same oracle.
        { CpuAccounting policy_cpu(stats[0]);
        for(int delay=0;delay<=8;delay++) {
            State current=state;int grounded=0;bool safe=true;
            std::memcpy(trace,current.v,88);
            for(int tick=1;tick<nt;tick++) {
                if(Clock::now()>=deadline)return -1;
                const double* row=world.row(tick);int mask=0;
                State neutral;step(current,0,row,world.platform(tick),np,neutral);
                if(neutral.v[6]!=0.) {
                    const double dir=neutral.v[7],angle=dir*(3.141592653589793/2.);
                    const double gx=std::cos(angle),gy=std::sin(angle);
                    const int jump=dir==0.?1:dir==1.?4:dir==2.?2:8;
                    if(row[6])grounded=0;
                    const bool touching=solid(neutral.v[0],neutral.v[1],neutral.v[3],dir,row,world.platform(tick),np,gx,gy);
                    if(touching){grounded++;if(!(int(current.v[4])&jump) && grounded>delay)mask=jump;}
                    else{grounded=0;if(int(current.v[4])&jump)mask=jump;}
                }
                State following;step(current,mask,row,world.platform(tick),np,following);
                if(collision(world,tick,following)){safe=false;break;}
                current=following;actions[tick-1]=mask;std::memcpy(trace+tick*11,current.v,88);
            }
            if(safe){*controller_delay=delay;stats[0].expanded=nt-1;stats[0].generated=nt-1;stats[0].unique=nt-1;
                stats[0].reached=nt-1;stats[0].status=1;stats[0].workspace_bytes=3*sizeof(State);return 0;}
        }
        }
        std::atomic<int> next(0),best(jobs);std::atomic<bool> failed(false);
        const int word_stride=std::max(1,nt-1);
        std::vector<int64_t> words(size_t(jobs)*word_stride);
        auto work=[&](){try {while(true){int job=next.fetch_add(1);if(job>=jobs || job>best.load())break;
            probe(world,state,controls,counts,stride,widths[job],seeds[job],job,best,deadline,words.data()+size_t(job)*word_stride,stats[job],std::max(1,workers/std::min(workers,jobs)));}}
            catch(...){failed.store(true);}};
        std::vector<std::thread> threads;JoinThreads joiner{threads};
        for(int i=1;i<std::min(workers,jobs);i++)threads.emplace_back(work);
        work();for(auto& thread:threads)thread.join();
        if(failed.load())return -3;
        int winner=best.load();if(winner>=jobs)return -1;
        CpuAccounting replay_cpu(stats[winner]);
        std::copy_n(words.data()+size_t(winner)*word_stride,nt-1,actions);
        std::memcpy(trace,state.v,88);
        for(int tick=1;tick<nt;tick++){State out;step(state,int(actions[tick-1]),world.row(tick),world.platform(tick),np,out);state=out;std::memcpy(trace+tick*11,state.v,88);}
        return winner;
    }catch(...){return -3;}
}
}
