from __future__ import annotations # treat all type hints as strings for now , Do NOT evaluate them immediately
from dataclasses import dataclass
from states import states_graph,heuristic
import heapq


@dataclass
class Node:
    state:str
    parent:Node=None
    path_cost:int=0
    depth: int=0

def reconstruct_path(goal:Node):
    path=[]
    while goal is not None:
        path.append(goal.state)
        goal=goal.parent
    return path[::-1]

# ========= Uninformed Search ============

def BFS(start,goal):
    frontier =[Node(state=start)]
    reached={start}
    visited =set()
    while frontier:
        curr = frontier.pop(0)

        visited.add(curr.state)
        
        if curr.state==goal:
            return curr

        for neighbor, cost in sorted(states_graph[curr.state]):
            print(f'Current state: {neighbor}: ',end=' ')
            if neighbor not in visited and neighbor not in reached:
                print("State isn't explored!..add to frontier")
                reached.add(neighbor)
                new_node = Node(
                                state=neighbor,
                                parent=curr,
                                path_cost=curr.path_cost+cost,
                                depth=curr.depth+1
                        )
                frontier.append(new_node)
            else: print("State already explored!")
    return None

def DFS(start,goal):
    frontier =[Node(state=start)]
    reached={start}
    visited =set()
    while frontier:
        curr = frontier.pop(-1)

        visited.add(curr.state)
        
        if curr.state==goal:
            return curr

        for neighbor, cost in sorted(states_graph[curr.state],reverse=True):
            print(f'Current state: {neighbor}: ',end=' ')
            if neighbor not in visited and neighbor not in reached:
                print("State isn't explored!..add to frontier")
                reached.add(neighbor)
                new_node = Node(
                                state=neighbor,
                                parent=curr,
                                path_cost=curr.path_cost+cost,
                                depth=curr.depth+1
                        )
                frontier.append(new_node)
            else: print("State already explored!")
    return None

def DLS(start,goal,limit):
    frontier =[Node(state=start)]
    reached={start}
    visited =set()
    while frontier:
        curr = frontier.pop(-1)

        visited.add(curr.state)
        
        if curr.state==goal:
            return curr

        if curr.depth<limit:
            for neighbor, cost in sorted(states_graph[curr.state],reverse=True):
                print(f'Current state: {neighbor}: ',end=' ')
                if neighbor not in visited and neighbor not in reached:
                    print("State isn't explored!..add to frontier")
                    reached.add(neighbor)
                    new_node = Node(
                                    state=neighbor,
                                    parent=curr,
                                    path_cost=curr.path_cost+cost,
                                    depth=curr.depth+1
                            )
                    frontier.append(new_node)
                else: print("State already explored!")
    return None

def IDS(start,goal,maxLimit):
    for limit in range(maxLimit+1):

        print(f'=== Trying with depth = {limit} ====')

        result = DLS(start,goal,limit)

        if result is not None : return result

    return None

def g_n(currNode:Node,edgeCost:int):
    return currNode.path_cost+edgeCost

def UCS(start,goal,cost_function=g_n):
    frontier=[(0,start,Node(state=start))]

    #best(lowest) cost so far for each state
    
    least_cost={start:0}

    while frontier:
        currCost , _ , curr = heapq.heappop(frontier)

        if curr.state==goal:
            return curr

        if currCost > least_cost.get(curr.state,float('inf')):
            continue

        for neighbor , edge_cost in states_graph[curr.state]:
            newCost= cost_function(curr,edge_cost)
            if newCost < least_cost.get(neighbor,float('inf')):

                
                least_cost[neighbor]=newCost

                newNode = Node(state=neighbor,parent=curr,path_cost=newCost,depth=curr.depth+1)

                heapq.heappush(frontier,(newCost,neighbor,newNode))

    return None

def h_n(state:str):
    return heuristic[state]

# ============ Informed Search ===================

def greedy_best_first_Search(start,goal,cost_function=h_n):
    frontier = [(heuristic[start] ,start,Node(state=start))]
    reached ={start}
    visited=set()

    while frontier:
        _,_,curr = heapq.heappop(frontier)

        if curr.state == goal:
            return curr

        visited.add(curr.state)

        for neighbor , edgeCost in states_graph[curr.state]:
            if neighbor not in visited and neighbor not in reached:
                reached.add(neighbor)

                newNode= Node(state=neighbor,parent=curr,path_cost=curr.path_cost+edgeCost,depth=curr.depth+1)

                heapq.heappush(frontier,(cost_function(neighbor),neighbor,newNode))

    return None

def A_Star_search(start,goal):
    frontier=[(heuristic[start],start,Node(state=start))]

    least_g_cost_soFar={start:0}

    while frontier:
        _,_,curr = heapq.heappop(frontier)
        
        if curr.state==goal: return curr

        if curr.path_cost > least_g_cost_soFar.get(curr.state,float('inf')): continue

        for neighbor , edgeCost in states_graph[curr.state]:

            new_g= g_n(curr,edgeCost)

            if new_g < least_g_cost_soFar.get(neighbor,float('inf')):

                least_g_cost_soFar[neighbor] = new_g

                NewNode=Node(state=neighbor,parent=curr,path_cost=new_g,depth=curr.depth+1)
                f_n = heuristic[neighbor] + new_g

                heapq.heappush(frontier,(f_n,neighbor,NewNode)) 

    return None


# shortest actual path cost from any node to the goal
def actual_trueCost(goal):
    
    
    least_true_cost={goal:0}
    frontier=[(0,goal)]

    while frontier:

        currCost , curr = heapq.heappop(frontier)

        if currCost > least_true_cost.get(curr,float('inf')): continue

        for neighbor , edgeCost in states_graph[curr]:

            newCost = currCost+edgeCost
            if newCost < least_true_cost.get(curr,float('inf')):

                least_true_cost[neighbor] =newCost

                heapq.heappush(frontier,(newCost,neighbor))

    return least_true_cost


def isAdmissible(goal):
    true_cost = actual_trueCost(goal)

    for state in states_graph:
        h_n = heuristic[state]
        h_star = true_cost[state]

        if h_n > h_star: return False

    return True

def isConsistent(goal):

    if heuristic[goal]!=0: return False

    for node ,edges in states_graph:
        h_n = heuristic[node]
        for neighbor , edgeCost in edges:
            h_nPrime = heuristic[neighbor]

            if h_n > (edgeCost+h_nPrime): return False

    return True

def A_Star_search_with_limit(start,goal,threshold):
    frontier=[(heuristic[start],start,Node(state=start))]

    least_g_cost_soFar={start:0}
    mi_pruned_f=float('inf')
    while frontier:
        fn,_,curr = frontier.pop(-1)
        
        if fn > threshold : 
            mi_pruned_f=min(mi_pruned_f,fn)
            continue
        if curr.state==goal: return curr,None


        if curr.path_cost > least_g_cost_soFar.get(curr.state,float('inf')): continue

        for neighbor , edgeCost in states_graph[curr.state]:

            new_g= g_n(curr,edgeCost)

            if new_g < least_g_cost_soFar.get(neighbor,float('inf')):

                least_g_cost_soFar[neighbor] = new_g

                NewNode=Node(state=neighbor,parent=curr,path_cost=new_g,depth=curr.depth+1)
                f_n = heuristic[neighbor] + new_g

                frontier.append((f_n,neighbor,NewNode)) 

    return None,mi_pruned_f


def IDA(start,goal,f_Threshold):
     while True:
        res,f_pruned = A_Star_search_with_limit(start,goal,f_Threshold)
        if res == None and f_pruned!=float('inf'):
            f_Threshold=f_pruned
        else: return res
 
