import datetime
import discord
import json
import os
import pickle
import logging
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger('auction_bot')

class Auction:
    """Class representing an auction"""
    def __init__(
        self, 
        id: int, 
        item_name: str, 
        starting_bid: int, 
        bid_increment: int,
        duration_seconds: int,
        creator_id: int,
        channel_id: int,
        currency: str = "coins",
        emblem_url: str = None,
        anonymous_bidding: bool = False,
        auto_delete_emblem: bool = False
    ):
        self.id = id
        self.item_name = item_name
        self.starting_bid = starting_bid
        self.bid_increment = bid_increment
        self.highest_bid = starting_bid
        self.highest_bidder_id = None
        self.highest_bidder_name = None
        self.created_at = datetime.datetime.now()
        self.end_time = self.created_at + datetime.timedelta(seconds=duration_seconds)
        self.ended = False
        self.cancelled = False
        self.creator_id = creator_id
        self.channel_id = channel_id
        self.message_id = None
        self.bid_history = []
        self.currency = currency
        self.emblem_url = emblem_url
        self.best_offer = starting_bid  # Track best offer separately
        self.anonymous_bidding = anonymous_bidding  # Whether bidders remain anonymous
        self.auto_delete_emblem = auto_delete_emblem  # Whether to delete emblem when auction ends
    
    def place_bid(self, bidder_id: int, bidder_name: str, bid_amount: int) -> bool:
        """Place a bid on this auction"""
        # Don't allow bids on ended auctions
        if self.ended:
            return False
        
        # Don't allow bids that aren't higher than the current highest bid
        if bid_amount <= self.highest_bid:
            return False
        
        # Don't allow bids that aren't at least the bid increment higher
        if self.highest_bidder_id is not None and bid_amount < self.highest_bid + self.bid_increment:
            return False
        
        # Update the highest bid
        self.highest_bid = bid_amount
        self.highest_bidder_id = bidder_id
        self.highest_bidder_name = bidder_name
        
        # Add to bid history
        self.bid_history.append({
            "bidder_id": bidder_id,
            "bidder_name": bidder_name,
            "amount": bid_amount,
            "time": datetime.datetime.now()
        })
        
        return True
    
    def is_ended(self) -> bool:
        """Check if the auction has ended"""
        if self.ended:
            return True
        
        # Check if the end time has passed
        now = datetime.datetime.now()
        if now >= self.end_time:
            return True
        
        return False


class AuctionManager:
    """Class for managing multiple auctions"""
    def __init__(self):
        self.auctions: Dict[int, Auction] = {}
        self.next_id = 1
        self.data_file = "auction_data.pickle"
        self.load_data()
        
    def save_data(self):
        """Save auction data to file"""
        try:
            with open(self.data_file, 'wb') as f:
                pickle.dump({
                    'auctions': self.auctions,
                    'next_id': self.next_id
                }, f)
            logger.info(f"Saved auction data to {self.data_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save auction data: {e}")
            return False
            
    def load_data(self):
        """Load auction data from file"""
        if not os.path.exists(self.data_file):
            logger.info(f"No auction data file found at {self.data_file}")
            return False
            
        try:
            with open(self.data_file, 'rb') as f:
                data = pickle.load(f)
                self.auctions = data.get('auctions', {})
                self.next_id = data.get('next_id', 1)
            logger.info(f"Loaded auction data from {self.data_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to load auction data: {e}")
            return False
    
    def create_auction(
        self, 
        item_name: str, 
        starting_bid: int, 
        bid_increment: int,
        duration_seconds: int,
        creator_id: int,
        channel_id: int,
        currency: str = "coins",
        emblem_url: str = None,
        anonymous_bidding: bool = False,
        auto_delete_emblem: bool = False
    ) -> int:
        """Create a new auction and return its ID"""
        auction_id = self.next_id
        self.next_id += 1
        
        auction = Auction(
            id=auction_id,
            item_name=item_name,
            starting_bid=starting_bid,
            bid_increment=bid_increment,
            duration_seconds=duration_seconds,
            creator_id=creator_id,
            channel_id=channel_id,
            currency=currency,
            emblem_url=emblem_url,
            anonymous_bidding=anonymous_bidding,
            auto_delete_emblem=auto_delete_emblem
        )
        
        self.auctions[auction_id] = auction
        return auction_id
    
    def get_auction(self, auction_id: int) -> Optional[Auction]:
        """Get an auction by ID"""
        return self.auctions.get(auction_id)
    
    def set_message_id(self, auction_id: int, message_id: int) -> bool:
        """Set the message ID for an auction"""
        auction = self.get_auction(auction_id)
        if not auction:
            return False
        
        auction.message_id = message_id
        return True
    
    def end_auction(self, auction_id: int, cancelled: bool = False) -> bool:
        """End an auction"""
        auction = self.get_auction(auction_id)
        if not auction:
            return False
        
        auction.ended = True
        auction.cancelled = cancelled
        return True
    
    def get_active_auctions(self) -> Dict[int, Auction]:
        """Get all active auctions"""
        return {id: auction for id, auction in self.auctions.items() if not auction.ended}
    
    def get_ended_auctions(self) -> List[int]:
        """Get IDs of auctions that have ended but haven't been processed yet"""
        ended_auctions = []
        for auction_id, auction in self.auctions.items():
            if not auction.ended and auction.is_ended():
                ended_auctions.append(auction_id)
        return ended_auctions
    
    def create_auction_embed(self, auction: Auction) -> discord.Embed:
        """Create an embed for an auction"""
        if auction.ended:
            title = f"Auction: {auction.item_name} [ENDED]"
            color = discord.Color.red()
        else:
            title = f"Auction: {auction.item_name}"
            color = discord.Color.gold()
        
        embed = discord.Embed(
            title=title,
            description=f"Place your bids for this item!",
            color=color
        )
        
        # Set emblem image if available and not auto-deleted
        if auction.emblem_url and not (auction.ended and auction.auto_delete_emblem):
            embed.set_thumbnail(url=auction.emblem_url)
        
        # Get owner name
        try:
            from discord.ext import commands
            bot = commands.Bot.get_instance()
            owner = bot.get_user(auction.creator_id)
            owner_name = owner.name if owner else f"User ID: {auction.creator_id}"
        except:
            owner_name = f"User ID: {auction.creator_id}"
        
        # Add owner field
        embed.add_field(
            name="Owner", 
            value=owner_name, 
            inline=True
        )
        
        # Add currency field
        embed.add_field(
            name="Currency", 
            value=auction.currency, 
            inline=True
        )
        
        # Add auction details
        embed.add_field(
            name="Starting Bid", 
            value=f"{auction.starting_bid} {auction.currency}", 
            inline=True
        )
        
        # Add best offer (current highest bid)
        if auction.highest_bidder_id:
            embed.add_field(
                name="Best Offer", 
                value=f"{auction.highest_bid} {auction.currency}", 
                inline=True
            )
        else:
            embed.add_field(
                name="Best Offer", 
                value=f"{auction.starting_bid} {auction.currency} (Starting Bid)", 
                inline=True
            )
        
        # Add bid increment
        embed.add_field(
            name="Bid Increment", 
            value=f"{auction.bid_increment} {auction.currency}", 
            inline=True
        )
        
        # Add auction ID
        embed.add_field(
            name="Auction ID", 
            value=str(auction.id), 
            inline=True
        )
        
        # Add highest bidder info
        if auction.highest_bidder_id:
            if auction.anonymous_bidding:
                embed.add_field(
                    name="Highest Bidder", 
                    value="Anonymous", 
                    inline=True
                )
            else:
                embed.add_field(
                    name="Highest Bidder", 
                    value=auction.highest_bidder_name, 
                    inline=True
                )
        else:
            embed.add_field(
                name="Highest Bidder", 
                value="None", 
                inline=True
            )
        
        # Add time information
        end_timestamp = int(auction.end_time.timestamp())
        embed.add_field(
            name="End Time", 
            value=f"<t:{end_timestamp}:R> (<t:{end_timestamp}:F>)", 
            inline=False
        )
        
        # Add footer with instructions
        embed.set_footer(
            text=f"Click the 'Place Bid' button to bid. Minimum bid increment: {auction.bid_increment} {auction.currency}"
        )
        
        return embed
